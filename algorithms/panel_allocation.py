import math
from database import get_db_connection

def allocate_review_panels(num_panels=3, faculty_per_panel=3, avoid_mentor_evaluator=True, review_code='REV-01'):
    """
    Automatically allocates review panels with faculty members and student teams.
    - Balances number of teams per panel equally.
    - Distributes faculty members across panels fairly.
    - Integrates mentor visibility for all teams.
    - Avoids assigning a team's own mentor as its evaluator when avoid_mentor_evaluator=True.
    - Records in review_panels, panel_faculty, and team_reviews.
    """
    if num_panels < 1 or faculty_per_panel < 1:
        raise ValueError("Panels and faculty count per panel must be at least 1.")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Fetch active faculty
            cursor.execute("SELECT id, faculty_id, name, specialization FROM faculty WHERE is_active = 1 ORDER BY id ASC")
            faculty_list = cursor.fetchall()

            if len(faculty_list) < num_panels:
                return {
                    'success': False,
                    'message': f'Not enough faculty members ({len(faculty_list)}) for {num_panels} panels. Add more faculty.',
                    'panels_count': 0
                }

            # 2. Fetch all teams along with their assigned mentors
            cursor.execute("""
                SELECT t.id, t.team_id, t.team_name, t.strength, 
                       ma.faculty_id AS mentor_id, f.name AS mentor_name
                FROM teams t
                LEFT JOIN mentor_allocations ma ON t.team_id = ma.team_id
                LEFT JOIN faculty f ON ma.faculty_id = f.faculty_id
                ORDER BY t.team_id ASC
            """)
            teams = cursor.fetchall()

            if not teams:
                return {
                    'success': False,
                    'message': 'No teams found to allocate to panels. Please form teams first.',
                    'panels_count': 0
                }

            # 3. Check or ensure the target review exists (e.g., Review 1)
            cursor.execute("SELECT id, review_code, review_name FROM reviews WHERE review_code = %s", (review_code,))
            review = cursor.fetchone()
            if not review:
                cursor.execute("""
                    INSERT INTO reviews (review_code, review_name, description, max_total_marks, weightage_percent, status)
                    VALUES (%s, 'Review 1', 'First Project Phase Progress & Requirement Analysis Review', 100.00, 30.00, 'Scheduled')
                """, (review_code,))
                review_id = cursor.lastrowid
            else:
                review_id = review['id']

            # 4. Clear existing panels and allocations for clean re-generation
            cursor.execute("DELETE FROM panel_faculty")
            cursor.execute("DELETE FROM team_reviews WHERE review_id = %s", (review_id,))
            cursor.execute("DELETE FROM review_panels")

            # 5. Create panels
            panels = []
            for p in range(1, num_panels + 1):
                panel_id = f"PANEL-{p:02d}"
                panel_name = f"Review Panel {p}"
                venue = f"Conference Hall {chr(64 + p)}"  # Hall A, Hall B, Hall C
                cursor.execute("""
                    INSERT INTO review_panels (panel_id, panel_name, venue, description)
                    VALUES (%s, %s, %s, %s)
                """, (panel_id, panel_name, venue, f"Evaluation Committee for Mini Project Review {p}"))
                panels.append({
                    'panel_id': panel_id,
                    'panel_name': panel_name,
                    'venue': venue,
                    'faculty': [],
                    'teams': []
                })

            # 6. Distribute faculty across panels
            fac_idx = 0
            total_fac = len(faculty_list)
            for p_idx in range(num_panels):
                panel = panels[p_idx]
                for f_slot in range(faculty_per_panel):
                    fac = faculty_list[fac_idx % total_fac]
                    role = 'Chairperson' if f_slot == 0 else 'Member'
                    
                    cursor.execute("""
                        INSERT INTO panel_faculty (panel_id, faculty_id, role)
                        VALUES (%s, %s, %s)
                    """, (panel['panel_id'], fac['faculty_id'], role))
                    
                    panel['faculty'].append({
                        'faculty_id': fac['faculty_id'],
                        'name': fac['name'],
                        'role': role
                    })
                    fac_idx += 1

            # 7. Distribute teams across panels equally with mentor conflict avoidance
            panel_team_counts = {p['panel_id']: 0 for p in panels}
            panel_faculty_map = {
                p['panel_id']: [f['faculty_id'] for f in p['faculty']] 
                for p in panels
            }

            for team in teams:
                team_id = team['team_id']
                mentor_id = team.get('mentor_id')

                # Candidate panels sorted by least assigned teams
                candidate_panels = sorted(panels, key=lambda p: panel_team_counts[p['panel_id']])
                
                chosen_panel = None
                if avoid_mentor_evaluator and mentor_id:
                    # Look for panel where mentor is NOT a member
                    for cp in candidate_panels:
                        if mentor_id not in panel_faculty_map[cp['panel_id']]:
                            chosen_panel = cp
                            break

                # If no conflict-free panel found or avoidance not strictly required, pick least loaded
                if not chosen_panel:
                    chosen_panel = candidate_panels[0]

                p_id = chosen_panel['panel_id']
                panel_team_counts[p_id] += 1
                chosen_panel['teams'].append(team)

                # Insert into team_reviews
                cursor.execute("""
                    INSERT INTO team_reviews (review_id, team_id, panel_id, scheduled_date, venue, status)
                    VALUES (%s, %s, %s, CURDATE(), %s, 'Pending')
                """, (review_id, team_id, p_id, chosen_panel['venue']))

            conn.commit()
            return {
                'success': True,
                'message': f'Successfully allocated {len(panels)} review panels with faculty and balanced teams.',
                'panels_count': len(panels),
                'panels': panels
            }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
