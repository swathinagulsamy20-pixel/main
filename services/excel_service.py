import os
import re
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from database import get_db_connection
from werkzeug.security import generate_password_hash

def clean_text(val):
    if val is None or pd.isna(val):
        return ''
    return ' '.join(str(val).strip().split())

def parse_students_excel(file_path, academic_year='2025-2026'):
    """
    Parses student Excel files and maps fields strictly:
    - roll_number: actual student roll number (e.g. 25ITR138, 25ITR179)
    - student_name & name: actual student name (e.g. SRI MANIKANDAPRABHU S, YASHVANTH P S)
    - grade_category: 'Grade A' or 'Grade B'
    - S.No / Serial Number: COMPLETELY IGNORED and NEVER stored as roll_number or student_name.
    Uses ON DUPLICATE KEY UPDATE on roll_number to update existing records without creating duplicates.
    """
    df_raw = pd.read_excel(file_path, header=None)
    students_to_insert = []
    seen_roll_numbers = set()

    # Find the header row containing 'Roll Number' / 'Roll No' and 'Name'
    header_row_idx = None
    for r_idx in range(min(15, len(df_raw))):
        row_vals = [str(cell).strip().lower() for cell in df_raw.iloc[r_idx] if pd.notna(cell)]
        has_roll = any('roll' in v or 'reg' in v for v in row_vals)
        has_name = any('name' in v and 'department' not in v for v in row_vals)
        if has_roll and has_name:
            header_row_idx = r_idx
            break

    if header_row_idx is not None:
        header_row = df_raw.iloc[header_row_idx]
        cat_row = df_raw.iloc[header_row_idx - 1] if header_row_idx > 0 else None

        # Detect roll and name column indices, strictly ignoring S.No columns
        roll_cols = []
        name_cols = []
        for c_idx, cell in enumerate(header_row):
            if pd.notna(cell):
                c_str = str(cell).strip().lower()
                # Explicitly ignore S.No / Serial No columns!
                if 's.no' in c_str or 'sno' in c_str or 'serial' in c_str:
                    continue
                if 'roll' in c_str or 'reg' in c_str:
                    roll_cols.append(c_idx)
                elif 'name' in c_str and 'department' not in c_str:
                    name_cols.append(c_idx)

        # Pair up roll and name columns (supports side-by-side Grade A and Grade B)
        col_pairs = []
        for r_col in roll_cols:
            matching_name = None
            for n_col in name_cols:
                if n_col > r_col:
                    matching_name = n_col
                    break
            if matching_name is not None:
                # Detect Grade A or Grade B from category row above
                cat = 'Grade A'
                if cat_row is not None:
                    for check_c in range(max(0, r_col - 1), min(len(cat_row), matching_name + 2)):
                        if pd.notna(cat_row.iloc[check_c]):
                            text_cat = str(cat_row.iloc[check_c]).strip().lower()
                            if 'b' in text_cat:
                                cat = 'Grade B'
                                break
                            elif 'a' in text_cat:
                                cat = 'Grade A'
                                break
                if (cat_row is None or cat_row.empty) or ('b' not in cat.lower() and len(col_pairs) == 1):
                    cat = 'Grade B' if len(col_pairs) == 1 else 'Grade A'

                col_pairs.append((r_col, matching_name, cat))

        # Extract student records
        for r in range(header_row_idx + 1, len(df_raw)):
            row = df_raw.iloc[r]
            for (r_col, n_col, cat) in col_pairs:
                if r_col < len(row) and n_col < len(row):
                    raw_roll = clean_text(row[r_col])
                    raw_name = clean_text(row[n_col])

                    # Verify raw_name is an actual name, NOT a serial number or header
                    if raw_name and not raw_name.isdigit() and raw_name.lower() not in ['name', 'nan', 'student name']:
                        # Verify raw_roll is an actual roll number, NOT a serial number
                        if raw_roll and raw_roll.lower() not in ['roll number', 'roll no', 'nan']:
                            roll_key = raw_roll.upper()
                            if roll_key not in seen_roll_numbers:
                                seen_roll_numbers.add(roll_key)
                                students_to_insert.append({
                                    'roll_number': roll_key,
                                    'student_name': raw_name,
                                    'name': raw_name,
                                    'grade_category': cat
                                })

    # Fallback for standard flat spreadsheets
    if not students_to_insert:
        xl = pd.ExcelFile(file_path)
        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)
            name_col = None
            roll_col = None
            grade_col = None

            for col in df.columns:
                c_low = str(col).lower()
                if 's.no' in c_low or 'sno' in c_low or 'serial' in c_low:
                    continue  # Explicitly ignore S.No!
                if 'roll' in c_low or 'reg' in c_low:
                    roll_col = col
                elif 'name' in c_low and not name_col:
                    name_col = col
                elif 'grade' in c_low or 'category' in c_low:
                    grade_col = col

            if name_col and roll_col:
                default_grade = 'Grade A' if 'a' in sheet_name.lower() else ('Grade B' if 'b' in sheet_name.lower() else 'Grade A')
                for _, row in df.iterrows():
                    name_val = clean_text(row[name_col])
                    roll_val = clean_text(row[roll_col])
                    if name_val and roll_val and not name_val.isdigit() and name_val.lower() not in ['name', 'nan']:
                        roll_key = roll_val.upper()
                        if roll_key not in seen_roll_numbers:
                            seen_roll_numbers.add(roll_key)
                            grade_val = clean_text(row[grade_col]) if grade_col else default_grade
                            cat = 'Grade B' if 'b' in grade_val.lower() else 'Grade A'
                            students_to_insert.append({
                                'roll_number': roll_key,
                                'student_name': name_val,
                                'name': name_val,
                                'grade_category': cat
                            })

    if not students_to_insert:
        raise ValueError("Could not find valid student records. Please ensure Roll Number and Student Name columns exist.")

    # Save to database using atomic ON DUPLICATE KEY UPDATE on roll_number
    conn = get_db_connection()
    inserted_count = 0
    updated_count = 0
    try:
        with conn.cursor() as cursor:
            for s in students_to_insert:
                cursor.execute("""
                    INSERT INTO students (roll_number, name, grade_category, academic_year, is_assigned)
                    VALUES (%s, %s, %s, %s, 0)
                    ON DUPLICATE KEY UPDATE 
                        name = VALUES(name),
                        grade_category = VALUES(grade_category),
                        academic_year = VALUES(academic_year)
                """, (s['roll_number'], s['name'], s['grade_category'], academic_year))
                if cursor.rowcount == 1:
                    inserted_count += 1
                elif cursor.rowcount == 2:
                    updated_count += 1
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return {
        'total_found': len(students_to_insert),
        'inserted': inserted_count,
        'updated': updated_count,
        'grade_a_count': sum(1 for s in students_to_insert if s['grade_category'] == 'Grade A'),
        'grade_b_count': sum(1 for s in students_to_insert if s['grade_category'] == 'Grade B')
    }

def parse_faculty_excel(file_path):
    """
    Parses Faculty Excel files (e.g. Faculty_Details.xlsx) and inserts faculty members into database.
    Ignores S.No, extracts Faculty Name and Area of Specialization.
    Auto-generates Faculty ID (FAC001, FAC002, etc.) and login user account.
    """
    df_raw = pd.read_excel(file_path, header=None)
    faculty_to_insert = []
    seen_faculty = set()

    # Look for header row containing NAME and SPECIALIZATION
    header_idx = None
    name_col = 1
    spec_col = 2

    for r_idx in range(min(10, len(df_raw))):
        row_str = " ".join([str(v).lower() for v in df_raw.iloc[r_idx] if pd.notna(v)])
        if 'name' in row_str and ('specialization' in row_str or 'area' in row_str):
            header_idx = r_idx
            # detect exact col indices
            for c_idx, cell in enumerate(df_raw.iloc[r_idx]):
                c_str = str(cell).lower()
                if 'name' in c_str and not 'department' in c_str:
                    name_col = c_idx
                elif 'specialization' in c_str or 'area' in c_str:
                    spec_col = c_idx
            break

    start_row = (header_idx + 1) if header_idx is not None else 1

    for r in range(start_row, len(df_raw)):
        row = df_raw.iloc[r]
        if name_col < len(row):
            name_val = clean_text(row[name_col])
            # Ignore headers, digits, empty
            if name_val and name_val.lower() not in ['name', 'nan', 'faculty name'] and not name_val.isdigit():
                if name_val.lower() not in seen_faculty:
                    seen_faculty.add(name_val.lower())
                    spec_val = clean_text(row[spec_col]) if spec_col < len(row) else 'Computer Science'
                    if not spec_val or spec_val.lower() == 'nan':
                        spec_val = 'Information Technology & Engineering'
                    faculty_to_insert.append({
                        'name': name_val,
                        'specialization': spec_val
                    })

    if not faculty_to_insert:
        raise ValueError("Could not find faculty records in uploaded Excel file.")

    conn = get_db_connection()
    inserted_count = 0
    default_password_hash = generate_password_hash('password123')
    try:
        with conn.cursor() as cursor:
            # Get max existing faculty_id
            cursor.execute("SELECT faculty_id FROM faculty ORDER BY id DESC LIMIT 1")
            last_fac = cursor.fetchone()
            curr_num = 1
            if last_fac and last_fac['faculty_id'].startswith('FAC'):
                try:
                    curr_num = int(last_fac['faculty_id'].replace('FAC', '')) + 1
                except:
                    curr_num = 1

            for f in faculty_to_insert:
                cursor.execute("SELECT id, faculty_id FROM faculty WHERE name = %s", (f['name'],))
                existing = cursor.fetchone()
                if existing:
                    cursor.execute("""
                        UPDATE faculty 
                        SET specialization = %s 
                        WHERE id = %s
                    """, (f['specialization'], existing['id']))
                else:
                    fac_id = f"FAC{curr_num:03d}"
                    curr_num += 1
                    cursor.execute("""
                        INSERT INTO faculty (faculty_id, name, specialization, max_mentees, current_mentees, is_active)
                        VALUES (%s, %s, %s, 4, 0, 1)
                    """, (fac_id, f['name'], f['specialization']))
                    inserted_count += 1

                    # Create login user account
                    username = fac_id.lower()
                    cursor.execute("""
                        INSERT INTO users (username, password_hash, role, full_name, linked_id)
                        VALUES (%s, %s, 'mentor', %s, %s)
                        ON DUPLICATE KEY UPDATE full_name = %s
                    """, (username, default_password_hash, f['name'], fac_id, f['name']))

            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return {
        'total_found': len(faculty_to_insert),
        'inserted': inserted_count
    }

# -------------------------------------------------------------
# Report Generation: Excel Exporters (OpenPyXL styled)
# -------------------------------------------------------------

def apply_excel_styling(ws, title, headers, rows):
    """Applies modern aesthetic styling to an openpyxl worksheet."""
    # Title styling
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.font = Font(name='Segoe UI', size=16, bold=True, color='FFFFFF')
    title_cell.fill = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid') # Deep Indigo
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 40

    # Header styling
    header_fill = PatternFill(start_color='3B82F6', end_color='3B82F6', fill_type='solid') # Vibrant Blue
    header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    thin_border = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    for col_idx, header in enumerate(headers, start=1):
        c = ws.cell(row=2, column=col_idx, value=header)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border = thin_border
    ws.row_dimensions[2].height = 28

    # Data rows styling
    alt_fill = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')
    data_font = Font(name='Segoe UI', size=10)

    for r_idx, row in enumerate(rows, start=3):
        is_alt = (r_idx % 2 == 0)
        ws.row_dimensions[r_idx].height = 22
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.font = data_font
            cell.border = thin_border
            if is_alt:
                cell.fill = alt_fill
            # Align center for codes/dates, left for names
            if str(val).startswith('25ITP') or str(val).startswith('FAC') or str(val).startswith('PANEL'):
                cell.alignment = Alignment(horizontal='center', vertical='center')
            else:
                cell.alignment = Alignment(horizontal='left', vertical='center')

    # Auto-adjust column widths
    from openpyxl.utils import get_column_letter
    for col_idx, col in enumerate(ws.columns, start=1):
        max_len = max(len(str(cell.value or '')) for cell in col if not str(type(cell)).endswith('MergedCell\'>'))
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 15)

def export_students_to_excel(output_path):
    """
    Export students to Excel with actual Roll Number and Student Name.
    S.No is completely ignored.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT s.roll_number, s.name AS student_name, 
                       s.grade_category, COALESCE(tm.team_id, 'Not Assigned') AS team_id
                FROM students s
                LEFT JOIN team_members tm ON s.id = tm.student_id
                ORDER BY s.grade_category ASC, s.roll_number ASC
            """)
            students = cursor.fetchall()
            
            wb = Workbook()
            ws = wb.active
            ws.title = "Student Directory"

            headers = ["Roll Number", "Student Name", "Grade Category", "Assigned Team ID"]
            rows = [[s['roll_number'], s['student_name'], s['grade_category'], s['team_id']] for s in students]

            apply_excel_styling(ws, "Student Directory - Grade A & Grade B", headers, rows)
            wb.save(output_path)
            return output_path
    finally:
        conn.close()

def export_teams_to_excel(output_path):
    """Export formed teams and members with Team IDs (e.g. 25ITP001)."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT t.team_id, t.strength, t.grade_a_count, t.grade_b_count,
                       COALESCE(f.name, 'Not Allocated') AS mentor_name,
                       GROUP_CONCAT(CONCAT(s.name, IF(tm.is_leader=1, ' (Leader)', '')) SEPARATOR ', ') AS members
                FROM teams t
                LEFT JOIN team_members tm ON t.team_id = tm.team_id
                LEFT JOIN students s ON tm.student_id = s.id
                LEFT JOIN mentor_allocations ma ON t.team_id = ma.team_id
                LEFT JOIN faculty f ON ma.faculty_id = f.faculty_id
                GROUP BY t.team_id, t.strength, t.grade_a_count, t.grade_b_count, f.name
                ORDER BY t.team_id ASC
            """)
            teams = cursor.fetchall()

            wb = Workbook()
            ws = wb.active
            ws.title = "Team Formations"

            headers = ["Team ID", "Strength", "Grade A Count", "Grade B Count", "Assigned Mentor", "Team Members"]
            rows = [[t['team_id'], t['strength'], t['grade_a_count'], t['grade_b_count'], t['mentor_name'], t['members']] for t in teams]

            apply_excel_styling(ws, "Student Team Formations & Allocations", headers, rows)
            wb.save(output_path)
            return output_path
    finally:
        conn.close()

def export_faculty_to_excel(output_path):
    """Export faculty details and specializations."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT faculty_id, name, specialization, current_mentees, max_mentees FROM faculty ORDER BY faculty_id ASC")
            faculty = cursor.fetchall()

            wb = Workbook()
            ws = wb.active
            ws.title = "Faculty Directory"

            headers = ["Faculty ID", "Faculty Name", "Area of Specialization", "Current Mentees", "Max Capacity"]
            rows = [[f['faculty_id'], f['name'], f['specialization'], f['current_mentees'], f['max_mentees']] for f in faculty]

            apply_excel_styling(ws, "Faculty Directory & Specializations", headers, rows)
            wb.save(output_path)
            return output_path
    finally:
        conn.close()

def export_panels_to_excel(output_path):
    """Export review panels, assigned faculty, and teams with their mentors."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT rp.panel_id, rp.panel_name, rp.venue,
                       GROUP_CONCAT(DISTINCT CONCAT(f.name, ' (', pf.role, ')') SEPARATOR '; ') AS faculty_members,
                       GROUP_CONCAT(DISTINCT CONCAT(tr.team_id, ' [Mentor: ', COALESCE(mf.name, 'None'), ']') SEPARATOR '; ') AS assigned_teams
                FROM review_panels rp
                LEFT JOIN panel_faculty pf ON rp.panel_id = pf.panel_id
                LEFT JOIN faculty f ON pf.faculty_id = f.faculty_id
                LEFT JOIN team_reviews tr ON rp.panel_id = tr.panel_id
                LEFT JOIN mentor_allocations ma ON tr.team_id = ma.team_id
                LEFT JOIN faculty mf ON ma.faculty_id = mf.faculty_id
                GROUP BY rp.panel_id, rp.panel_name, rp.venue
                ORDER BY rp.panel_id ASC
            """)
            panels = cursor.fetchall()

            wb = Workbook()
            ws = wb.active
            ws.title = "Review Panels"

            headers = ["Panel ID", "Panel Name", "Venue", "Panel Faculty & Roles", "Assigned Teams & Mentors"]
            rows = [[p['panel_id'], p['panel_name'], p['venue'], p['faculty_members'] or 'None', p['assigned_teams'] or 'None'] for p in panels]

            apply_excel_styling(ws, "Review Panel Allocation with Faculty & Mentors", headers, rows)
            wb.save(output_path)
            return output_path
    finally:
        conn.close()

def export_review_marks_to_excel(output_path, review_code='REV-01'):
    """Export review marks sheet with criteria breakdown."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT tr.team_id, tr.panel_id, r.review_name, tr.status, tr.total_score,
                       tr.general_comments, COALESCE(mf.name, 'None') AS mentor_name
                FROM team_reviews tr
                JOIN reviews r ON tr.review_id = r.id
                LEFT JOIN mentor_allocations ma ON tr.team_id = ma.team_id
                LEFT JOIN faculty mf ON ma.faculty_id = mf.faculty_id
                WHERE r.review_code = %s
                ORDER BY tr.team_id ASC
            """, (review_code,))
            reviews = cursor.fetchall()

            wb = Workbook()
            ws = wb.active
            ws.title = "Review Marks"

            headers = ["Team ID", "Panel", "Review", "Status", "Total Score", "Mentor", "Comments"]
            rows = [[
                r['team_id'], r['panel_id'], r['review_name'], r['status'], 
                r['total_score'] if r['total_score'] is not None else 'Pending', 
                r['mentor_name'], r['general_comments'] or ''
            ] for r in reviews]

            apply_excel_styling(ws, f"Evaluation Marks Sheet - {review_code}", headers, rows)
            wb.save(output_path)
            return output_path
    finally:
        conn.close()
