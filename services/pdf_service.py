import os
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from database import get_db_connection

def get_base_styles():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E3A8A'),
        alignment=1, # Center
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748B'),
        alignment=1,
        spaceAfter=15
    )
    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1E293B')
    )
    cell_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white,
        alignment=1
    )
    return styles, title_style, subtitle_style, cell_style, cell_header_style

def generate_students_pdf(output_path):
    """
    Generate PDF report for Students.
    Displays actual Roll Number, Student Name, Grade Category, and Assigned Team ID. NO S.No column!
    """
    doc = SimpleDocTemplate(output_path, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles, title_style, subtitle_style, cell_style, cell_header_style = get_base_styles()
    story = []

    story.append(Paragraph("Smart Mini Project Management System", title_style))
    story.append(Paragraph("Student Roster — Grade A & Grade B Directory", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=15))

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

            data = [[
                Paragraph("Roll Number", cell_header_style),
                Paragraph("Student Name", cell_header_style),
                Paragraph("Grade Category", cell_header_style),
                Paragraph("Assigned Team ID", cell_header_style)
            ]]

            for s in students:
                data.append([
                    Paragraph(f"<b>{s['roll_number']}</b>", cell_style),
                    Paragraph(s['student_name'], cell_style),
                    Paragraph(f"<font color='{'#059669' if s['grade_category']=='Grade A' else '#D97706'}'><b>{s['grade_category']}</b></font>", cell_style),
                    Paragraph(s['team_id'], cell_style)
                ])

            table = Table(data, colWidths=[110, 230, 100, 100])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ]))
            story.append(table)
    finally:
        conn.close()

    doc.build(story)
    return output_path

def generate_teams_pdf(output_path):
    """Generate PDF report for Teams and Assigned Members with Team IDs (e.g. 25ITP001)."""
    doc = SimpleDocTemplate(output_path, pagesize=landscape(letter), leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles, title_style, subtitle_style, cell_style, cell_header_style = get_base_styles()
    story = []

    story.append(Paragraph("Smart Mini Project Management System", title_style))
    story.append(Paragraph("Automated Team Formations & Student Allocations", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=15))

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

            data = [[
                Paragraph("Team ID", cell_header_style),
                Paragraph("Strength", cell_header_style),
                Paragraph("Grade Ratio (A:B)", cell_header_style),
                Paragraph("Assigned Mentor", cell_header_style),
                Paragraph("Team Members (Names Only)", cell_header_style)
            ]]

            for t in teams:
                data.append([
                    Paragraph(f"<b>{t['team_id']}</b>", cell_style),
                    Paragraph(str(t['strength']), cell_style),
                    Paragraph(f"A: {t['grade_a_count']} | B: {t['grade_b_count']}", cell_style),
                    Paragraph(t['mentor_name'], cell_style),
                    Paragraph(t['members'] or 'No members', cell_style)
                ])

            table = Table(data, colWidths=[90, 60, 110, 150, 310])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ]))
            story.append(table)
    finally:
        conn.close()

    doc.build(story)
    return output_path

def generate_panels_pdf(output_path):
    """Generate PDF report for Review Panels with Faculty & Mentors."""
    doc = SimpleDocTemplate(output_path, pagesize=landscape(letter), leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles, title_style, subtitle_style, cell_style, cell_header_style = get_base_styles()
    story = []

    story.append(Paragraph("Smart Mini Project Management System", title_style))
    story.append(Paragraph("Review Panel Allocations with Faculty Committee & Team Mentors", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=15))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT rp.panel_id, rp.panel_name, rp.venue,
                       GROUP_CONCAT(DISTINCT CONCAT(f.name, ' (', pf.role, ')') SEPARATOR '<br/>') AS faculty_members,
                       GROUP_CONCAT(DISTINCT CONCAT('<b>', tr.team_id, '</b> [Mentor: ', COALESCE(mf.name, 'Unassigned'), ']') SEPARATOR '<br/>') AS assigned_teams
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

            data = [[
                Paragraph("Panel ID", cell_header_style),
                Paragraph("Panel Details", cell_header_style),
                Paragraph("Evaluation Committee", cell_header_style),
                Paragraph("Assigned Teams & Their Mentors", cell_header_style)
            ]]

            for p in panels:
                data.append([
                    Paragraph(f"<b>{p['panel_id']}</b>", cell_style),
                    Paragraph(f"<b>{p['panel_name']}</b><br/>Venue: {p['venue']}", cell_style),
                    Paragraph(p['faculty_members'] or 'No faculty assigned', cell_style),
                    Paragraph(p['assigned_teams'] or 'No teams allocated', cell_style)
                ])

            table = Table(data, colWidths=[90, 160, 230, 240])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ]))
            story.append(table)
    finally:
        conn.close()

    doc.build(story)
    return output_path

def generate_review_marks_pdf(output_path, review_code='REV-01'):
    """Generate PDF for Review Marks & Evaluation Results."""
    doc = SimpleDocTemplate(output_path, pagesize=landscape(letter), leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles, title_style, subtitle_style, cell_style, cell_header_style = get_base_styles()
    story = []

    story.append(Paragraph("Smart Mini Project Management System", title_style))
    story.append(Paragraph(f"Review Evaluation Marks & Results — {review_code}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E1'), spaceAfter=15))

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

            data = [[
                Paragraph("Team ID", cell_header_style),
                Paragraph("Panel", cell_header_style),
                Paragraph("Mentor", cell_header_style),
                Paragraph("Evaluation Status", cell_header_style),
                Paragraph("Total Marks", cell_header_style),
                Paragraph("Faculty Remarks", cell_header_style)
            ]]

            for r in reviews:
                score_display = f"<b>{r['total_score']} / 100</b>" if r['total_score'] is not None else "<font color='#64748B'>Pending</font>"
                data.append([
                    Paragraph(f"<b>{r['team_id']}</b>", cell_style),
                    Paragraph(r['panel_id'], cell_style),
                    Paragraph(r['mentor_name'], cell_style),
                    Paragraph(f"<b>{r['status']}</b>", cell_style),
                    Paragraph(score_display, cell_style),
                    Paragraph(r['general_comments'] or 'No remarks recorded', cell_style)
                ])

            table = Table(data, colWidths=[90, 80, 150, 110, 90, 200])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ]))
            story.append(table)
    finally:
        conn.close()

    doc.build(story)
    return output_path
