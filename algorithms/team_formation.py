import math
from database import get_db_connection
from config import Config

def form_teams_fair_distribution(team_strength=3, team_prefix='25ITP', academic_year='2025-2026', clear_existing=True):
    """
    Automate team formation with fair distribution of Grade A and Grade B students.
    Generates sequential Team IDs formatted like '25ITP001', '25ITP002', etc.
    Executes within an atomic database transaction.
    """
    if team_strength < 1:
        raise ValueError("Team strength must be at least 1.")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Fetch unassigned students categorized by grade
            cursor.execute("""
                SELECT id, name, roll_number, grade_category 
                FROM students 
                WHERE is_assigned = 0 
                ORDER BY grade_category ASC, id ASC
            """)
            students = cursor.fetchall()
            
            if not students:
                # If clear_existing is True and all students are already assigned, we will check total students
                cursor.execute("""
                    SELECT id, name, roll_number, grade_category 
                    FROM students 
                    ORDER BY grade_category ASC, id ASC
                """)
                students = cursor.fetchall()

            if not students:
                return {
                    'success': False,
                    'message': 'No students available to form teams. Please upload student details first.',
                    'teams_formed': 0
                }

            if clear_existing:
                # Remove existing team members and teams
                cursor.execute("DELETE FROM team_members")
                cursor.execute("DELETE FROM teams")
                cursor.execute("UPDATE students SET is_assigned = 0")

            grade_a_students = [s for s in students if s['grade_category'] == 'Grade A']
            grade_b_students = [s for s in students if s['grade_category'] == 'Grade B']

            total_students = len(students)
            num_teams = math.ceil(total_students / team_strength)
            if num_teams == 0:
                num_teams = 1

            # Prepare team buckets
            team_buckets = [[] for _ in range(num_teams)]

            # 1. Fairly distribute Grade A students round-robin across teams
            team_idx = 0
            for student in grade_a_students:
                team_buckets[team_idx % num_teams].append(student)
                team_idx += 1

            # 2. Fairly distribute Grade B students to balance the teams
            # Sort buckets by current size ascending so smallest teams get B students first
            for student in grade_b_students:
                # Find bucket with minimum count that hasn't reached max capacity
                min_bucket = min(team_buckets, key=lambda b: len(b))
                min_bucket.append(student)

            # Filter out empty buckets if any
            active_teams = [b for b in team_buckets if len(b) > 0]

            # 3. Insert teams and team members into database
            created_teams = []
            for i, members in enumerate(active_teams, start=1):
                team_id = f"{team_prefix}{i:03d}"  # e.g., 25ITP001, 25ITP002
                a_count = sum(1 for m in members if m['grade_category'] == 'Grade A')
                b_count = sum(1 for m in members if m['grade_category'] == 'Grade B')
                strength = len(members)

                # Insert into teams table
                cursor.execute("""
                    INSERT INTO teams (team_id, team_name, strength, grade_a_count, grade_b_count, academic_year, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'Formed')
                """, (team_id, f"Team {i}", strength, a_count, b_count, academic_year))

                # Insert team members
                for idx, member in enumerate(members):
                    is_leader = 1 if idx == 0 else 0
                    cursor.execute("""
                        INSERT INTO team_members (team_id, student_id, roll_number, is_leader)
                        VALUES (%s, %s, %s, %s)
                    """, (team_id, member['id'], member.get('roll_number'), is_leader))
                    
                    # Mark student as assigned
                    cursor.execute("UPDATE students SET is_assigned = 1 WHERE id = %s", (member['id'],))

                created_teams.append({
                    'team_id': team_id,
                    'strength': strength,
                    'grade_a_count': a_count,
                    'grade_b_count': b_count,
                    'member_count': len(members)
                })

            conn.commit()
            return {
                'success': True,
                'message': f'Successfully formed {len(created_teams)} teams with fair Grade A & B distribution.',
                'teams_count': len(created_teams),
                'teams': created_teams
            }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
