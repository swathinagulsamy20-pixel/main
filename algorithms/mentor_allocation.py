from database import get_db_connection

def allocate_mentors_automatically(clear_existing=True):
    """
    Automatically allocates faculty mentors to student teams based on:
    1. Faculty specialization matching team project domain / keywords
    2. Mentoring workload balancing (distributing mentees evenly)
    3. Respecting max_mentees capacity per faculty member
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Fetch all active faculty members
            cursor.execute("""
                SELECT id, faculty_id, name, specialization, max_mentees, current_mentees 
                FROM faculty 
                WHERE is_active = 1 
                ORDER BY current_mentees ASC, id ASC
            """)
            faculty_list = cursor.fetchall()

            if not faculty_list:
                return {
                    'success': False,
                    'message': 'No active faculty found. Please upload or add faculty details first.',
                    'allocations_count': 0
                }

            # 2. Fetch all teams
            cursor.execute("""
                SELECT id, team_id, project_title, domain 
                FROM teams 
                ORDER BY team_id ASC
            """)
            teams = cursor.fetchall()

            if not teams:
                return {
                    'success': False,
                    'message': 'No teams found. Please form teams first.',
                    'allocations_count': 0
                }

            if clear_existing:
                cursor.execute("DELETE FROM mentor_allocations")
                cursor.execute("UPDATE faculty SET current_mentees = 0")
                for f in faculty_list:
                    f['current_mentees'] = 0

            # Map faculty workload tracker
            faculty_workload = {f['faculty_id']: 0 for f in faculty_list}
            if not clear_existing:
                cursor.execute("SELECT faculty_id, COUNT(*) as cnt FROM mentor_allocations WHERE status = 'Active' GROUP BY faculty_id")
                for row in cursor.fetchall():
                    if row['faculty_id'] in faculty_workload:
                        faculty_workload[row['faculty_id']] = row['cnt']

            # Match and assign
            allocations = []
            for team in teams:
                team_id = team['team_id']
                team_domain = (team.get('domain') or team.get('project_title') or '').lower()

                # Score faculty: lower current_mentees gets priority, domain match gives bonus
                scored_faculty = []
                for f in faculty_list:
                    fac_id = f['faculty_id']
                    curr = faculty_workload[fac_id]
                    max_m = f['max_mentees'] if f['max_mentees'] > 0 else 4

                    # Check if over max capacity
                    if curr >= max_m:
                        score = 1000 + curr  # Penalty if over capacity
                    else:
                        score = curr * 10    # Prefer faculty with fewer mentees

                    # Check specialization keyword match if team has domain specified
                    if team_domain and team_domain in f['specialization'].lower():
                        score -= 5  # Bonus for specialization match

                    scored_faculty.append((score, fac_id, f))

                scored_faculty.sort(key=lambda x: x[0])
                chosen_fac = scored_faculty[0][2]
                chosen_id = chosen_fac['faculty_id']

                # Insert or update mentor_allocations
                cursor.execute("""
                    INSERT INTO mentor_allocations (team_id, faculty_id, allocation_type, status)
                    VALUES (%s, %s, 'Auto', 'Active')
                    ON DUPLICATE KEY UPDATE faculty_id = %s, allocation_type = 'Auto', status = 'Active'
                """, (team_id, chosen_id, chosen_id))

                faculty_workload[chosen_id] += 1
                allocations.append({
                    'team_id': team_id,
                    'faculty_id': chosen_id,
                    'faculty_name': chosen_fac['name'],
                    'specialization': chosen_fac['specialization']
                })

            # Update current_mentees in faculty table
            for fac_id, count in faculty_workload.items():
                cursor.execute("UPDATE faculty SET current_mentees = %s WHERE faculty_id = %s", (count, fac_id))

            conn.commit()
            return {
                'success': True,
                'message': f'Successfully allocated mentors to {len(allocations)} teams with balanced workload.',
                'allocations_count': len(allocations),
                'allocations': allocations
            }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
