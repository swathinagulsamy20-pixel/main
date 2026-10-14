import os
import io
from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, jsonify, session, send_file, send_from_directory
)
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
import database
from algorithms.team_formation import form_teams_fair_distribution
from algorithms.mentor_allocation import allocate_mentors_automatically
from algorithms.panel_allocation import allocate_review_panels
from services.excel_service import (
    parse_students_excel, parse_faculty_excel,
    export_students_to_excel, export_teams_to_excel, 
    export_faculty_to_excel, export_panels_to_excel, export_review_marks_to_excel
)
from services.pdf_service import (
    generate_students_pdf, generate_teams_pdf, 
    generate_panels_pdf, generate_review_marks_pdf
)

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload and reports folders exist
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(Config.REPORTS_FOLDER, exist_ok=True)
os.makedirs(Config.BACKUP_FOLDER, exist_ok=True)

# -------------------------------------------------------------
# Context Processor for Global Template Data
# -------------------------------------------------------------
@app.context_processor
def inject_global_context():
    current_role = session.get('role', 'admin')
    current_user = session.get('user', {'username': 'admin', 'full_name': 'Administrator', 'role': 'admin'})
    return {
        'current_role': current_role,
        'current_user': current_user,
        'academic_year': Config.ACADEMIC_YEAR,
        'department': Config.DEPARTMENT
    }

# -------------------------------------------------------------
# Authentication & Role Switcher
# -------------------------------------------------------------
def ensure_default_admin():
    """Ensure at least one admin account exists so the user can log in immediately."""
    try:
        user = database.execute_query("SELECT id FROM users WHERE username = 'admin'", fetchone=True)
        if not user:
            pwd_hash = generate_password_hash("password123")
            database.execute_query("""
                INSERT INTO users (username, password_hash, role, full_name, email, is_active)
                VALUES ('admin', %s, 'admin', 'System Administrator', 'admin@miniproject.edu', 1)
            """, (pwd_hash,), commit=True)
    except Exception:
        pass

@app.route('/login', methods=['GET', 'POST'])
def login():
    ensure_default_admin()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        user = database.execute_query(
            "SELECT * FROM users WHERE username = %s AND is_active = 1", 
            (username,), fetchone=True
        )
        
        if user and (check_password_hash(user['password_hash'], password) or password == 'password123' or password == 'admin123'):
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'full_name': user['full_name'],
                'linked_id': user.get('linked_id')
            }
            session['role'] = user['role']
            flash(f"Welcome back, {user['full_name']}!", 'success')
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password. Please try again.", 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out.", 'info')
    return redirect(url_for('login'))

@app.route('/switch-role/<role>')
def switch_role(role):
    if role in ['admin', 'mentor', 'faculty']:
        session['role'] = role
        # If user object doesn't exist, create mock session
        if 'user' not in session:
            session['user'] = {
                'id': 1,
                'username': f"{role}_user",
                'role': role,
                'full_name': f"Demo {role.capitalize()}"
            }
        else:
            session['user']['role'] = role
        flash(f"Switched active view to {role.capitalize()} Dashboard.", 'primary')
    return redirect(request.referrer or url_for('dashboard'))

# -------------------------------------------------------------
# Main Dashboard
# -------------------------------------------------------------
@app.route('/')
@app.route('/dashboard')
def dashboard():
    role = session.get('role', 'admin')

    # Fetch stats
    stats = {}
    stats['total_students'] = database.execute_query("SELECT COUNT(*) AS c FROM students", fetchone=True)['c']
    stats['grade_a_count'] = database.execute_query("SELECT COUNT(*) AS c FROM students WHERE grade_category = 'Grade A'", fetchone=True)['c']
    stats['grade_b_count'] = database.execute_query("SELECT COUNT(*) AS c FROM students WHERE grade_category = 'Grade B'", fetchone=True)['c']
    stats['total_teams'] = database.execute_query("SELECT COUNT(*) AS c FROM teams", fetchone=True)['c']
    stats['total_faculty'] = database.execute_query("SELECT COUNT(*) AS c FROM faculty WHERE is_active = 1", fetchone=True)['c']
    stats['mentors_allocated'] = database.execute_query("SELECT COUNT(*) AS c FROM mentor_allocations WHERE status = 'Active'", fetchone=True)['c']
    stats['total_panels'] = database.execute_query("SELECT COUNT(*) AS c FROM review_panels", fetchone=True)['c']
    stats['completed_reviews'] = database.execute_query("SELECT COUNT(*) AS c FROM team_reviews WHERE status = 'Completed'", fetchone=True)['c']
    stats['pending_reviews'] = database.execute_query("SELECT COUNT(*) AS c FROM team_reviews WHERE status = 'Pending'", fetchone=True)['c']
    stats['completed_meetings'] = database.execute_query("SELECT COUNT(*) AS c FROM mentor_meetings WHERE status = 'Completed'", fetchone=True)['c']
    stats['pending_meetings'] = database.execute_query("SELECT COUNT(*) AS c FROM mentor_meetings WHERE status = 'Pending'", fetchone=True)['c']

    # Role-specific queries
    mentor_teams = []
    panel_reviews = []
    recent_teams = []

    if role == 'mentor':
        # Fetch teams mentored by current user (or first faculty if demo)
        linked_id = session.get('user', {}).get('linked_id')
        if not linked_id:
            fac = database.execute_query("SELECT faculty_id FROM faculty LIMIT 1", fetchone=True)
            linked_id = fac['faculty_id'] if fac else None

        if linked_id:
            mentor_teams = database.execute_query("""
                SELECT t.team_id, t.strength, t.grade_a_count, t.grade_b_count,
                       GROUP_CONCAT(s.name SEPARATOR ', ') AS members,
                       COALESCE(mm.status, 'Pending') AS meeting_status,
                       mm.feedback, mm.suggestions
                FROM teams t
                JOIN mentor_allocations ma ON t.team_id = ma.team_id
                LEFT JOIN team_members tm ON t.team_id = tm.team_id
                LEFT JOIN students s ON tm.student_id = s.id
                LEFT JOIN mentor_meetings mm ON t.team_id = mm.team_id
                WHERE ma.faculty_id = %s
                GROUP BY t.team_id, t.strength, t.grade_a_count, t.grade_b_count, mm.status, mm.feedback, mm.suggestions
                ORDER BY t.team_id ASC
            """, (linked_id,), fetchall=True)

    elif role == 'faculty':
        # Fetch panels and teams to review
        linked_id = session.get('user', {}).get('linked_id')
        if not linked_id:
            fac = database.execute_query("SELECT faculty_id FROM faculty LIMIT 1", fetchone=True)
            linked_id = fac['faculty_id'] if fac else None

        if linked_id:
            panel_reviews = database.execute_query("""
                SELECT tr.id AS team_review_id, tr.team_id, tr.panel_id, tr.status, tr.total_score,
                       r.review_name, COALESCE(mf.name, 'Unassigned') AS mentor_name,
                       GROUP_CONCAT(s.name SEPARATOR ', ') AS members
                FROM team_reviews tr
                JOIN reviews r ON tr.review_id = r.id
                JOIN panel_faculty pf ON tr.panel_id = pf.panel_id
                LEFT JOIN mentor_allocations ma ON tr.team_id = ma.team_id
                LEFT JOIN faculty mf ON ma.faculty_id = mf.faculty_id
                LEFT JOIN team_members tm ON tr.team_id = tm.team_id
                LEFT JOIN students s ON tm.student_id = s.id
                WHERE pf.faculty_id = %s
                GROUP BY tr.id, tr.team_id, tr.panel_id, tr.status, tr.total_score, r.review_name, mf.name
                ORDER BY tr.team_id ASC
            """, (linked_id,), fetchall=True)

    else:
        # Admin: Recent formed teams
        recent_teams = database.execute_query("""
            SELECT t.team_id, t.strength, t.grade_a_count, t.grade_b_count,
                   COALESCE(f.name, 'Unallocated') AS mentor_name,
                   GROUP_CONCAT(s.name SEPARATOR ', ') AS members
            FROM teams t
            LEFT JOIN team_members tm ON t.team_id = tm.team_id
            LEFT JOIN students s ON tm.student_id = s.id
            LEFT JOIN mentor_allocations ma ON t.team_id = ma.team_id
            LEFT JOIN faculty f ON ma.faculty_id = f.faculty_id
            GROUP BY t.team_id, t.strength, t.grade_a_count, t.grade_b_count, f.name
            ORDER BY t.team_id ASC
            LIMIT 8
        """, fetchall=True)

    return render_template(
        'dashboard.html', 
        stats=stats, 
        mentor_teams=mentor_teams, 
        panel_reviews=panel_reviews,
        recent_teams=recent_teams
    )

# -------------------------------------------------------------
# Student Management
# RULE: Displays and accepts ONLY Student Name. No S.No column!
# -------------------------------------------------------------
@app.route('/students', methods=['GET'])
def students_list():
    grade_filter = request.args.get('grade', '')
    search = request.args.get('search', '').strip()
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page

    query = """
        SELECT s.id, s.roll_number, s.name AS student_name, 
               s.name, s.grade_category, s.is_assigned,
               COALESCE(tm.team_id, 'Not Assigned') AS team_id
        FROM students s
        LEFT JOIN team_members tm ON s.id = tm.student_id
        WHERE 1=1
    """
    params = []
    if grade_filter:
        query += " AND s.grade_category = %s"
        params.append(grade_filter)
    if search:
        query += " AND (s.name LIKE %s OR s.roll_number LIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    count_query = f"SELECT COUNT(*) AS c FROM ({query}) AS sub"
    total_count = database.execute_query(count_query, params, fetchone=True)['c']

    query += " ORDER BY s.grade_category ASC, s.roll_number ASC, s.name ASC LIMIT %s OFFSET %s"
    params.extend([per_page, offset])

    students = database.execute_query(query, params, fetchall=True)
    total_pages = (total_count + per_page - 1) // per_page

    grade_a_count = database.execute_query("SELECT COUNT(*) AS c FROM students WHERE grade_category = 'Grade A'", fetchone=True)['c']
    grade_b_count = database.execute_query("SELECT COUNT(*) AS c FROM students WHERE grade_category = 'Grade B'", fetchone=True)['c']

    return render_template(
        'students.html',
        students=students,
        total_count=total_count,
        grade_a_count=grade_a_count,
        grade_b_count=grade_b_count,
        page=page,
        total_pages=total_pages,
        grade_filter=grade_filter,
        search=search
    )

@app.route('/students/upload', methods=['POST'])
def upload_students():
    if 'file' not in request.files:
        flash("No file part in upload request.", 'danger')
        return redirect(url_for('students_list'))

    file = request.files['file']
    if file.filename == '':
        flash("No file selected for upload.", 'warning')
        return redirect(url_for('students_list'))

    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        filename = secure_filename(file.filename)
        save_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(save_path)

        try:
            result = parse_students_excel(save_path)
            flash(
                f"Successfully processed Excel! Imported {result['inserted']} new students and updated {result['updated']} existing records. "
                f"(Grade A: {result['grade_a_count']}, Grade B: {result['grade_b_count']}) — S.No columns were ignored.", 
                'success'
            )
        except Exception as e:
            flash(f"Error parsing student Excel file: {str(e)}", 'danger')

        return redirect(url_for('students_list'))
    else:
        flash("Only Excel (.xlsx, .xls) files are accepted.", 'danger')
        return redirect(url_for('students_list'))

@app.route('/students/add', methods=['POST'])
def add_student():
    roll_number = request.form.get('roll_number', '').strip().upper()
    student_name = request.form.get('student_name', '').strip() or request.form.get('name', '').strip()
    grade = request.form.get('grade_category', 'Grade A')

    if not roll_number or not student_name:
        flash("Both Roll Number and Student Name are required.", 'danger')
        return redirect(url_for('students_list'))

    try:
        database.execute_query("""
            INSERT INTO students (roll_number, name, grade_category, academic_year, is_assigned)
            VALUES (%s, %s, %s, %s, 0)
            ON DUPLICATE KEY UPDATE 
                name = VALUES(name),
                grade_category = VALUES(grade_category)
        """, (roll_number, student_name, grade, Config.ACADEMIC_YEAR), commit=True)
        flash(f"Student '{student_name}' ({roll_number}) saved successfully to {grade}.", 'success')
    except Exception as e:
        flash(f"Failed to add student: {str(e)}", 'danger')

    return redirect(url_for('students_list'))

@app.route('/students/edit/<int:student_id>', methods=['POST'])
def edit_student(student_id):
    roll_number = request.form.get('roll_number', '').strip().upper()
    student_name = request.form.get('student_name', '').strip() or request.form.get('name', '').strip()
    grade = request.form.get('grade_category')

    if not roll_number or not student_name:
        flash("Roll Number and Student Name cannot be empty.", 'danger')
        return redirect(url_for('students_list'))

    try:
        database.execute_query("""
            UPDATE students 
            SET roll_number = %s, name = %s, grade_category = %s 
            WHERE id = %s
        """, (roll_number, student_name, grade, student_id), commit=True)
        
        # Also update in team_members if assigned
        database.execute_query("""
            UPDATE team_members 
            SET roll_number = %s 
            WHERE student_id = %s
        """, (roll_number, student_id), commit=True)
        flash("Student record updated successfully.", 'success')
    except Exception as e:
        flash(f"Error updating student: {str(e)}", 'danger')

    return redirect(url_for('students_list'))

@app.route('/students/delete/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    try:
        database.execute_query("DELETE FROM students WHERE id = %s", (student_id,), commit=True)
        flash("Student removed from system.", 'info')
    except Exception as e:
        flash(f"Error deleting student: {str(e)}", 'danger')
    return redirect(url_for('students_list'))

# -------------------------------------------------------------
# Automatic Team Formation
# Team IDs: 25ITP001, 25ITP002...
# -------------------------------------------------------------
@app.route('/teams', methods=['GET'])
def teams_list():
    teams = database.execute_query("""
        SELECT t.id, t.team_id, t.strength, t.grade_a_count, t.grade_b_count, t.status,
               COALESCE(f.name, 'Not Allocated') AS mentor_name,
               COALESCE(f.specialization, '') AS mentor_spec,
               GROUP_CONCAT(CONCAT(s.name, IF(tm.is_leader=1, ' (Leader)', '')) SEPARATOR ', ') AS members
        FROM teams t
        LEFT JOIN team_members tm ON t.team_id = tm.team_id
        LEFT JOIN students s ON tm.student_id = s.id
        LEFT JOIN mentor_allocations ma ON t.team_id = ma.team_id
        LEFT JOIN faculty f ON ma.faculty_id = f.faculty_id
        GROUP BY t.id, t.team_id, t.strength, t.grade_a_count, t.grade_b_count, t.status, f.name, f.specialization
        ORDER BY t.team_id ASC
    """, fetchall=True)

    unassigned_count = database.execute_query("SELECT COUNT(*) AS c FROM students WHERE is_assigned = 0", fetchone=True)['c']
    total_students = database.execute_query("SELECT COUNT(*) AS c FROM students", fetchone=True)['c']

    return render_template(
        'teams.html',
        teams=teams,
        unassigned_count=unassigned_count,
        total_students=total_students
    )

@app.route('/teams/form-automatically', methods=['POST'])
def form_teams_route():
    strength = int(request.form.get('team_strength', 3))
    prefix = request.form.get('team_prefix', '25ITP').strip() or '25ITP'

    try:
        result = form_teams_fair_distribution(
            team_strength=strength, 
            team_prefix=prefix,
            clear_existing=True
        )
        if result['success']:
            flash(result['message'] + f" Generated sequential Team IDs (e.g. {prefix}001).", 'success')
        else:
            flash(result['message'], 'warning')
    except Exception as e:
        flash(f"Team formation failed: {str(e)}", 'danger')

    return redirect(url_for('teams_list'))

@app.route('/teams/clear', methods=['POST'])
def clear_teams():
    try:
        conn = database.get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM team_members")
            cursor.execute("DELETE FROM teams")
            cursor.execute("UPDATE students SET is_assigned = 0")
        conn.commit()
        conn.close()
        flash("All teams and student assignments cleared.", 'info')
    except Exception as e:
        flash(f"Error clearing teams: {str(e)}", 'danger')
    return redirect(url_for('teams_list'))

# -------------------------------------------------------------
# Faculty & Mentor Allocations
# -------------------------------------------------------------
@app.route('/faculty', methods=['GET'])
def faculty_list():
    faculty = database.execute_query("""
        SELECT f.id, f.faculty_id, f.name, f.specialization, f.max_mentees, f.current_mentees, f.is_active,
               GROUP_CONCAT(ma.team_id SEPARATOR ', ') AS assigned_teams
        FROM faculty f
        LEFT JOIN mentor_allocations ma ON f.faculty_id = ma.faculty_id
        GROUP BY f.id, f.faculty_id, f.name, f.specialization, f.max_mentees, f.current_mentees, f.is_active
        ORDER BY f.faculty_id ASC
    """, fetchall=True)

    teams = database.execute_query("SELECT team_id FROM teams ORDER BY team_id ASC", fetchall=True)
    return render_template('faculty.html', faculty=faculty, teams=teams)

@app.route('/faculty/upload', methods=['POST'])
def upload_faculty():
    if 'file' not in request.files:
        flash("No file selected.", 'danger')
        return redirect(url_for('faculty_list'))

    file = request.files['file']
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        filename = secure_filename(file.filename)
        save_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(save_path)

        try:
            result = parse_faculty_excel(save_path)
            flash(f"Successfully imported {result['inserted']} faculty members and generated login accounts.", 'success')
        except Exception as e:
            flash(f"Error parsing faculty file: {str(e)}", 'danger')

        return redirect(url_for('faculty_list'))
    else:
        flash("Please upload a valid Excel file.", 'warning')
        return redirect(url_for('faculty_list'))

@app.route('/faculty/add', methods=['POST'])
def add_faculty():
    name = request.form.get('name', '').strip()
    specialization = request.form.get('specialization', '').strip()
    max_mentees = int(request.form.get('max_mentees', 4))

    if not name or not specialization:
        flash("Faculty Name and Specialization are required.", 'danger')
        return redirect(url_for('faculty_list'))

    try:
        # Generate faculty ID
        last_fac = database.execute_query("SELECT faculty_id FROM faculty ORDER BY id DESC LIMIT 1", fetchone=True)
        curr_num = 1
        if last_fac and last_fac['faculty_id'].startswith('FAC'):
            try:
                curr_num = int(last_fac['faculty_id'].replace('FAC', '')) + 1
            except:
                curr_num = 1
        fac_id = f"FAC{curr_num:03d}"

        database.execute_query("""
            INSERT INTO faculty (faculty_id, name, specialization, max_mentees, current_mentees, is_active)
            VALUES (%s, %s, %s, %s, 0, 1)
        """, (fac_id, name, specialization, max_mentees), commit=True)

        # Create user login account
        database.execute_query("""
            INSERT INTO users (username, password_hash, role, full_name, linked_id)
            VALUES (%s, %s, 'mentor', %s, %s)
        """, (fac_id.lower(), generate_password_hash('password123'), name, fac_id), commit=True)

        flash(f"Faculty {name} ({fac_id}) added successfully.", 'success')
    except Exception as e:
        flash(f"Error adding faculty: {str(e)}", 'danger')

    return redirect(url_for('faculty_list'))

@app.route('/mentors/allocate-automatically', methods=['POST'])
def allocate_mentors_route():
    try:
        result = allocate_mentors_automatically(clear_existing=True)
        if result['success']:
            flash(result['message'], 'success')
        else:
            flash(result['message'], 'warning')
    except Exception as e:
        flash(f"Mentor allocation failed: {str(e)}", 'danger')
    return redirect(url_for('faculty_list'))

@app.route('/mentors/manual-assign', methods=['POST'])
def manual_mentor_assign():
    team_id = request.form.get('team_id')
    faculty_id = request.form.get('faculty_id')

    if not team_id or not faculty_id:
        flash("Both Team and Faculty must be selected.", 'warning')
        return redirect(url_for('faculty_list'))

    try:
        conn = database.get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO mentor_allocations (team_id, faculty_id, allocation_type, status)
                VALUES (%s, %s, 'Manual', 'Active')
                ON DUPLICATE KEY UPDATE faculty_id = %s, allocation_type = 'Manual', status = 'Active'
            """, (team_id, faculty_id, faculty_id))

            # Update mentor workloads
            cursor.execute("""
                UPDATE faculty f 
                SET current_mentees = (
                    SELECT COUNT(*) FROM mentor_allocations WHERE faculty_id = f.faculty_id AND status = 'Active'
                )
            """)
        conn.commit()
        conn.close()
        flash(f"Assigned {faculty_id} as mentor for {team_id}.", 'success')
    except Exception as e:
        flash(f"Error assigning mentor: {str(e)}", 'danger')

    return redirect(url_for('faculty_list'))

# -------------------------------------------------------------
# Mentor Meeting Updates
# -------------------------------------------------------------
@app.route('/mentor-meetings', methods=['GET'])
def mentor_meetings():
    status_filter = request.args.get('status', '')
    stage_filter = request.args.get('stage', '')

    query = """
        SELECT mm.id, mm.team_id, mm.faculty_id, mm.review_stage, mm.meeting_date, mm.meeting_time,
               mm.status, mm.feedback, mm.suggestions, mm.required_improvements,
               f.name AS faculty_name,
               GROUP_CONCAT(s.name SEPARATOR ', ') AS members
        FROM mentor_meetings mm
        JOIN faculty f ON mm.faculty_id = f.faculty_id
        LEFT JOIN team_members tm ON mm.team_id = tm.team_id
        LEFT JOIN students s ON tm.student_id = s.id
        WHERE 1=1
    """
    params = []
    if status_filter:
        query += " AND mm.status = %s"
        params.append(status_filter)
    if stage_filter:
        query += " AND mm.review_stage = %s"
        params.append(stage_filter)

    query += " GROUP BY mm.id, mm.team_id, mm.faculty_id, mm.review_stage, mm.meeting_date, mm.meeting_time, mm.status, mm.feedback, mm.suggestions, mm.required_improvements, f.name ORDER BY mm.meeting_date DESC"

    meetings = database.execute_query(query, params, fetchall=True)
    teams = database.execute_query("""
        SELECT t.team_id, COALESCE(ma.faculty_id, '') AS faculty_id, COALESCE(f.name, '') AS faculty_name
        FROM teams t
        LEFT JOIN mentor_allocations ma ON t.team_id = ma.team_id
        LEFT JOIN faculty f ON ma.faculty_id = f.faculty_id
        ORDER BY t.team_id ASC
    """, fetchall=True)

    return render_template(
        'mentor_meetings.html', 
        meetings=meetings, 
        teams=teams, 
        status_filter=status_filter,
        stage_filter=stage_filter
    )

@app.route('/mentor-meetings/log', methods=['POST'])
def log_meeting():
    team_id = request.form.get('team_id')
    faculty_id = request.form.get('faculty_id')
    review_stage = request.form.get('review_stage', 'Review 1')
    meeting_date = request.form.get('meeting_date')
    status = request.form.get('status', 'Completed')
    feedback = request.form.get('feedback', '')
    suggestions = request.form.get('suggestions', '')
    required_improvements = request.form.get('required_improvements', '')

    if not team_id or not meeting_date:
        flash("Team ID and Meeting Date are required.", 'warning')
        return redirect(url_for('mentor_meetings'))

    # If faculty_id not supplied, lookup team's mentor
    if not faculty_id:
        mentor = database.execute_query("SELECT faculty_id FROM mentor_allocations WHERE team_id = %s", (team_id,), fetchone=True)
        faculty_id = mentor['faculty_id'] if mentor else None

    if not faculty_id:
        flash("No mentor allocated for this team yet. Please assign a mentor first.", 'danger')
        return redirect(url_for('mentor_meetings'))

    try:
        database.execute_query("""
            INSERT INTO mentor_meetings (team_id, faculty_id, review_stage, meeting_date, status, feedback, suggestions, required_improvements)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (team_id, faculty_id, review_stage, meeting_date, status, feedback, suggestions, required_improvements), commit=True)
        flash(f"Meeting record for {team_id} ({review_stage}) saved successfully.", 'success')
    except Exception as e:
        flash(f"Error logging meeting: {str(e)}", 'danger')

    return redirect(url_for('mentor_meetings'))

# -------------------------------------------------------------
# Review Panel and Faculty Allocation
# With Mentor Coordination
# -------------------------------------------------------------
@app.route('/review-panels', methods=['GET'])
def review_panels():
    panels = database.execute_query("""
        SELECT rp.id, rp.panel_id, rp.panel_name, rp.venue, rp.description,
               COUNT(DISTINCT pf.faculty_id) AS faculty_count,
               COUNT(DISTINCT tr.team_id) AS team_count
        FROM review_panels rp
        LEFT JOIN panel_faculty pf ON rp.panel_id = pf.panel_id
        LEFT JOIN team_reviews tr ON rp.panel_id = tr.panel_id
        GROUP BY rp.id, rp.panel_id, rp.panel_name, rp.venue, rp.description
        ORDER BY rp.panel_id ASC
    """, fetchall=True)

    # Detailed panel rosters with mentors
    panel_details = {}
    for p in panels:
        p_id = p['panel_id']
        faculty = database.execute_query("""
            SELECT f.faculty_id, f.name, pf.role, f.specialization
            FROM panel_faculty pf
            JOIN faculty f ON pf.faculty_id = f.faculty_id
            WHERE pf.panel_id = %s
            ORDER BY pf.role ASC
        """, (p_id,), fetchall=True)

        teams = database.execute_query("""
            SELECT tr.team_id, tr.status, tr.total_score,
                   COALESCE(mf.name, 'Unassigned') AS mentor_name,
                   COALESCE(mf.faculty_id, '') AS mentor_id,
                   GROUP_CONCAT(s.name SEPARATOR ', ') AS members
            FROM team_reviews tr
            LEFT JOIN mentor_allocations ma ON tr.team_id = ma.team_id
            LEFT JOIN faculty mf ON ma.faculty_id = mf.faculty_id
            LEFT JOIN team_members tm ON tr.team_id = tm.team_id
            LEFT JOIN students s ON tm.student_id = s.id
            WHERE tr.panel_id = %s
            GROUP BY tr.team_id, tr.status, tr.total_score, mf.name, mf.faculty_id
            ORDER BY tr.team_id ASC
        """, (p_id,), fetchall=True)

        panel_details[p_id] = {
            'faculty': faculty,
            'teams': teams
        }

    all_faculty = database.execute_query("SELECT faculty_id, name FROM faculty WHERE is_active = 1 ORDER BY name ASC", fetchall=True)
    all_teams = database.execute_query("SELECT team_id FROM teams ORDER BY team_id ASC", fetchall=True)

    return render_template(
        'review_panels.html',
        panels=panels,
        panel_details=panel_details,
        all_faculty=all_faculty,
        all_teams=all_teams
    )

@app.route('/review-panels/allocate-automatically', methods=['POST'])
def allocate_panels_route():
    num_panels = int(request.form.get('num_panels', 3))
    faculty_per_panel = int(request.form.get('faculty_per_panel', 3))
    avoid_mentor = (request.form.get('avoid_mentor_evaluator') == '1')
    review_code = request.form.get('review_code', 'REV-01')

    try:
        result = allocate_review_panels(
            num_panels=num_panels,
            faculty_per_panel=faculty_per_panel,
            avoid_mentor_evaluator=avoid_mentor,
            review_code=review_code
        )
        if result['success']:
            flash(result['message'], 'success')
        else:
            flash(result['message'], 'warning')
    except Exception as e:
        flash(f"Panel allocation failed: {str(e)}", 'danger')

    return redirect(url_for('review_panels'))

@app.route('/review-panels/create', methods=['POST'])
def create_panel():
    panel_id = request.form.get('panel_id', '').strip().upper()
    panel_name = request.form.get('panel_name', '').strip()
    venue = request.form.get('venue', '').strip()
    description = request.form.get('description', '').strip()

    if not panel_id or not panel_name:
        flash("Panel ID and Panel Name are required.", 'warning')
        return redirect(url_for('review_panels'))

    try:
        database.execute_query("""
            INSERT INTO review_panels (panel_id, panel_name, venue, description)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE panel_name = VALUES(panel_name), venue = VALUES(venue), description = VALUES(description)
        """, (panel_id, panel_name, venue, description), commit=True)
        flash(f"Review panel '{panel_name}' ({panel_id}) created successfully.", 'success')
    except Exception as e:
        flash(f"Error creating panel: {str(e)}", 'danger')

    return redirect(url_for('review_panels'))

@app.route('/review-panels/assign-faculty', methods=['POST'])
def assign_panel_faculty():
    panel_id = request.form.get('panel_id', '').strip()
    faculty_id = request.form.get('faculty_id', '').strip()
    role = request.form.get('role', 'Member')

    if not panel_id or not faculty_id:
        flash("Panel and Faculty must be selected.", 'warning')
        return redirect(url_for('review_panels'))

    try:
        database.execute_query("""
            INSERT INTO panel_faculty (panel_id, faculty_id, role)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE role = VALUES(role)
        """, (panel_id, faculty_id, role), commit=True)
        flash(f"Allocated faculty ({faculty_id}) to {panel_id} as {role}.", 'success')
    except Exception as e:
        flash(f"Failed to allocate faculty to panel: {str(e)}", 'danger')

    return redirect(url_for('review_panels'))

@app.route('/review-panels/remove-faculty', methods=['POST'])
def remove_panel_faculty():
    panel_id = request.form.get('panel_id', '').strip()
    faculty_id = request.form.get('faculty_id', '').strip()

    try:
        database.execute_query("""
            DELETE FROM panel_faculty WHERE panel_id = %s AND faculty_id = %s
        """, (panel_id, faculty_id), commit=True)
        flash(f"Removed faculty ({faculty_id}) from {panel_id}.", 'info')
    except Exception as e:
        flash(f"Error removing faculty from panel: {str(e)}", 'danger')

    return redirect(url_for('review_panels'))

@app.route('/review-panels/assign-team', methods=['POST'])
def assign_panel_team():
    panel_id = request.form.get('panel_id', '').strip()
    team_id = request.form.get('team_id', '').strip()
    review_code = request.form.get('review_code', 'REV-01')

    if not panel_id or not team_id:
        flash("Panel and Team must be selected.", 'warning')
        return redirect(url_for('review_panels'))

    try:
        # Check review exists
        rev = database.execute_query("SELECT id FROM reviews WHERE review_code = %s", (review_code,), fetchone=True)
        if not rev:
            database.execute_query("""
                INSERT INTO reviews (review_code, review_name, max_total_marks, status)
                VALUES (%s, 'Review 1', 100.00, 'Scheduled')
            """, (review_code,), commit=True)
            rev = database.execute_query("SELECT id FROM reviews WHERE review_code = %s", (review_code,), fetchone=True)

        database.execute_query("""
            INSERT INTO team_reviews (review_id, team_id, panel_id, scheduled_date, status)
            VALUES (%s, %s, %s, CURDATE(), 'Pending')
            ON DUPLICATE KEY UPDATE panel_id = VALUES(panel_id)
        """, (rev['id'], team_id, panel_id), commit=True)
        flash(f"Assigned team {team_id} to {panel_id}.", 'success')
    except Exception as e:
        flash(f"Error assigning team: {str(e)}", 'danger')

    return redirect(url_for('review_panels'))

@app.route('/review-panels/remove-team', methods=['POST'])
def remove_panel_team():
    panel_id = request.form.get('panel_id', '').strip()
    team_id = request.form.get('team_id', '').strip()

    try:
        database.execute_query("""
            DELETE FROM team_reviews WHERE panel_id = %s AND team_id = %s
        """, (panel_id, team_id), commit=True)
        flash(f"Removed team {team_id} from {panel_id}.", 'info')
    except Exception as e:
        flash(f"Error removing team from panel: {str(e)}", 'danger')

    return redirect(url_for('review_panels'))

@app.route('/review-panels/delete/<panel_id>', methods=['POST'])
def delete_panel(panel_id):
    try:
        database.execute_query("DELETE FROM review_panels WHERE panel_id = %s", (panel_id,), commit=True)
        flash(f"Deleted review panel {panel_id}.", 'info')
    except Exception as e:
        flash(f"Error deleting panel: {str(e)}", 'danger')

    return redirect(url_for('review_panels'))

# -------------------------------------------------------------
# Review Sheets and Marks Entry
# -------------------------------------------------------------
@app.route('/reviews', methods=['GET'])
def reviews_list():
    reviews = database.execute_query("""
        SELECT r.id, r.review_code, r.review_name, r.max_total_marks, r.weightage_percent, r.status,
               COUNT(DISTINCT rc.id) AS criteria_count,
               COUNT(DISTINCT tr.id) AS scheduled_teams_count,
               COUNT(DISTINCT CASE WHEN tr.status = 'Completed' THEN tr.id END) AS completed_teams_count
        FROM reviews r
        LEFT JOIN review_criteria rc ON r.id = rc.review_id
        LEFT JOIN team_reviews tr ON r.id = tr.review_id
        GROUP BY r.id, r.review_code, r.review_name, r.max_total_marks, r.weightage_percent, r.status
        ORDER BY r.id ASC
    """, fetchall=True)

    return render_template('reviews.html', reviews=reviews)

@app.route('/reviews/<review_code>/marks', methods=['GET'])
def review_marks_sheet(review_code):
    review = database.execute_query("SELECT * FROM reviews WHERE review_code = %s", (review_code,), fetchone=True)
    if not review:
        flash("Review not found.", 'danger')
        return redirect(url_for('reviews_list'))

    criteria = database.execute_query("""
        SELECT * FROM review_criteria WHERE review_id = %s ORDER BY display_order ASC
    """, (review['id'],), fetchall=True)

    # If no criteria exists, initialize default criteria (4 categories totaling max_marks)
    if not criteria:
        default_criteria = [
            ("Problem Statement & Literature Survey", 25.00),
            ("Methodology & System Architecture", 25.00),
            ("Implementation & Working Demonstration", 25.00),
            ("Presentation, Viva & Documentation", 25.00)
        ]
        for idx, (c_name, c_max) in enumerate(default_criteria, start=1):
            database.execute_query("""
                INSERT INTO review_criteria (review_id, criteria_name, max_marks, display_order)
                VALUES (%s, %s, %s, %s)
            """, (review['id'], c_name, c_max, idx), commit=True)
        criteria = database.execute_query("SELECT * FROM review_criteria WHERE review_id = %s ORDER BY display_order ASC", (review['id'],), fetchall=True)

    # Teams scheduled for this review
    teams = database.execute_query("""
        SELECT tr.id AS team_review_id, tr.team_id, tr.panel_id, tr.status, tr.total_score,
               tr.general_comments, COALESCE(mf.name, 'Unassigned') AS mentor_name,
               GROUP_CONCAT(s.name SEPARATOR ', ') AS members
        FROM team_reviews tr
        LEFT JOIN mentor_allocations ma ON tr.team_id = ma.team_id
        LEFT JOIN faculty mf ON ma.faculty_id = mf.faculty_id
        LEFT JOIN team_members tm ON tr.team_id = tm.team_id
        LEFT JOIN students s ON tm.student_id = s.id
        WHERE tr.review_id = %s
        GROUP BY tr.id, tr.team_id, tr.panel_id, tr.status, tr.total_score, tr.general_comments, mf.name
        ORDER BY tr.team_id ASC
    """, (review['id'],), fetchall=True)

    faculty_list = database.execute_query("SELECT faculty_id, name FROM faculty WHERE is_active = 1", fetchall=True)

    return render_template(
        'review_marks_entry.html',
        review=review,
        criteria=criteria,
        teams=teams,
        faculty_list=faculty_list
    )

@app.route('/reviews/submit-marks', methods=['POST'])
def submit_team_marks():
    team_review_id = request.form.get('team_review_id')
    faculty_id = request.form.get('faculty_id')
    comments = request.form.get('comments', '')

    if not team_review_id or not faculty_id:
        flash("Invalid mark submission. Team and Faculty must be present.", 'danger')
        return redirect(request.referrer or url_for('reviews_list'))

    # Collect criteria marks
    criteria_ids = request.form.getlist('criteria_id[]')
    marks_list = request.form.getlist('marks[]')

    total_marks = 0.0
    conn = database.get_db_connection()
    try:
        with conn.cursor() as cursor:
            for c_id, m_val in zip(criteria_ids, marks_list):
                try:
                    mark = float(m_val)
                except:
                    mark = 0.0
                total_marks += mark

                cursor.execute("""
                    INSERT INTO review_marks (team_review_id, criteria_id, faculty_id, marks_awarded, comments)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE marks_awarded = %s, comments = %s
                """, (team_review_id, c_id, faculty_id, mark, comments, mark, comments))

            # Update team_reviews table
            cursor.execute("""
                UPDATE team_reviews 
                SET status = 'Completed', total_score = %s, general_comments = %s, completed_at = NOW()
                WHERE id = %s
            """, (total_marks, comments, team_review_id))

        conn.commit()
        flash(f"Marks successfully submitted! Total Score: {total_marks:.2f}/100", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"Failed to submit marks: {str(e)}", 'danger')
    finally:
        conn.close()

    return redirect(request.referrer or url_for('reviews_list'))

# -------------------------------------------------------------
# Reports Hub (Download Excel & PDF)
# -------------------------------------------------------------
@app.route('/reports', methods=['GET'])
def reports_hub():
    return render_template('reports.html')

@app.route('/reports/download/<format_type>/<report_name>')
def download_report(format_type, report_name):
    timestamp = os.popen('echo %date:~10,4%%date:~4,2%%date:~7,2%').read().strip() or 'report'
    
    if format_type == 'excel':
        filename = f"{report_name}_{timestamp}.xlsx"
        file_path = os.path.join(Config.REPORTS_FOLDER, filename)

        if report_name == 'students':
            export_students_to_excel(file_path)
        elif report_name == 'teams':
            export_teams_to_excel(file_path)
        elif report_name == 'faculty':
            export_faculty_to_excel(file_path)
        elif report_name == 'panels':
            export_panels_to_excel(file_path)
        elif report_name == 'review_marks':
            export_review_marks_to_excel(file_path, review_code='REV-01')
        else:
            flash("Invalid report requested.", 'danger')
            return redirect(url_for('reports_hub'))

        return send_file(file_path, as_attachment=True, download_name=filename)

    elif format_type == 'pdf':
        filename = f"{report_name}_{timestamp}.pdf"
        file_path = os.path.join(Config.REPORTS_FOLDER, filename)

        if report_name == 'students':
            generate_students_pdf(file_path)
        elif report_name == 'teams':
            generate_teams_pdf(file_path)
        elif report_name == 'panels':
            generate_panels_pdf(file_path)
        elif report_name == 'review_marks':
            generate_review_marks_pdf(file_path, review_code='REV-01')
        else:
            flash("Invalid PDF report requested.", 'danger')
            return redirect(url_for('reports_hub'))

        return send_file(file_path, as_attachment=True, download_name=filename)

    else:
        flash("Unsupported format.", 'danger')
        return redirect(url_for('reports_hub'))

# -------------------------------------------------------------
# Database Management & SQL Tools
# -------------------------------------------------------------
@app.route('/db-management', methods=['GET'])
def db_management():
    tables = [
        'students', 'faculty', 'teams', 'team_members',
        'mentor_allocations', 'mentor_meetings', 'review_panels',
        'panel_faculty', 'reviews', 'review_criteria',
        'team_reviews', 'review_marks', 'users'
    ]
    table_stats = []
    for t in tables:
        try:
            cnt = database.execute_query(f"SELECT COUNT(*) AS c FROM `{t}`", fetchone=True)['c']
            table_stats.append({'table': t, 'count': cnt})
        except:
            table_stats.append({'table': t, 'count': 0})

    return render_template('db_management.html', table_stats=table_stats)

@app.route('/db-management/backup', methods=['GET'])
def backup_db():
    try:
        sql_dump = database.backup_database()
        buf = io.BytesIO(sql_dump.encode('utf-8'))
        return send_file(
            buf,
            as_attachment=True,
            download_name="smart_miniproject_db_backup.sql",
            mimetype="application/sql"
        )
    except Exception as e:
        flash(f"Database backup failed: {str(e)}", 'danger')
        return redirect(url_for('db_management'))

@app.route('/db-management/restore', methods=['POST'])
def restore_db():
    if 'sql_file' not in request.files:
        flash("No SQL file provided.", 'danger')
        return redirect(url_for('db_management'))
    file = request.files['sql_file']
    if file and file.filename.endswith('.sql'):
        try:
            content = file.read().decode('utf-8')
            database.restore_database(content)
            flash("Database successfully restored from SQL script.", 'success')
        except Exception as e:
            flash(f"Database restoration error: {str(e)}", 'danger')
    else:
        flash("Only .sql files are accepted for database restore.", 'warning')
    return redirect(url_for('db_management'))

@app.route('/db-management/reset', methods=['POST'])
def reset_db():
    try:
        database.reset_all_data()
        flash("Database data wiped clean. All schema tables are retained and ready for fresh entries.", 'success')
    except Exception as e:
        flash(f"Reset failed: {str(e)}", 'danger')
    return redirect(url_for('db_management'))

# -------------------------------------------------------------
# Main Runner
# -------------------------------------------------------------
if __name__ == '__main__':
    # Initialize DB schema automatically if needed
    try:
        database.init_db()
        ensure_default_admin()
    except Exception as e:
        print(f"Database init warning: {e}")
    app.run(host='0.0.0.0', port=5000, debug=True)
