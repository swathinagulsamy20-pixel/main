# Smart Mini Project Management System

A comprehensive, automated web application built for the **Department of Information Technology** to streamline student team formation, mentor allocation, review panel scheduling, faculty evaluation, review marks management, and report generation.

---

## 🛠️ Technology Stack

- **Frontend:** HTML5, CSS3, JavaScript (ES6+), Bootstrap 5.3, FontAwesome 6, Modern Side View Dashboard
- **Backend:** Python Flask 3.1
- **Database:** MySQL (Relational schema with foreign keys, cascading rules, and indexes)
- **Excel Processing:** Pandas & OpenPyXL
- **Reports Engine:** ReportLab (PDF generation) & OpenPyXL (Excel generation)

---

## 📋 Key Features & Modules

### 1. Student Excel Upload & Entry
- Supports multi-category Excel files (such as `Project Category students.xlsx` with Grade A & Grade B columns).
- **Strict Formatting Rule:** Stores and displays **only the student name**. S.No and serial numbers are completely ignored across the student entry form, student list, and database import process.
- Prevents duplicates and validates student names.
- Filter students by Grade A, Grade B, or view all.

### 2. Automatic Team Formation with Sequential Team IDs
- Admin specifies desired team strength (e.g., 3 or 4 students per team).
- Fair distribution algorithm balances Grade A and Grade B students evenly across all teams.
- Automatically generates sequential Team IDs (e.g. `25ITP001`, `25ITP002`, `25ITP003`...).
- Automatically designates team leaders.
- Stored in `teams` and `team_members` relational tables.

### 3. Faculty Excel Upload & Mentor Allocation
- Upload faculty directory from `Faculty_Details.xlsx` (Faculty Name & Area of Specialization).
- Automatically generates unique Faculty IDs (e.g. `FAC001`, `FAC002`...).
- Automated Mentor Allocation balances mentoring workload (up to max mentee capacity) and matches faculty specialization with project domains.
- Supports manual mentor assignment overrides.

### 4. Mentor Meeting Updates
- Teams must meet assigned mentors prior to every project review stage.
- Tracks meeting dates, status (`Completed`, `Pending`, `Scheduled`), mentor feedback, recommendations, and required improvements.
- Stored in `mentor_meetings`.

### 5. Review Panel & Faculty Allocation (with Mentors)
- Admin specifies number of review panels and faculty members required per panel.
- Fairly balances teams and faculty members across panels.
- **Review panel allocation with mentors:** Clearly links and displays each team's assigned mentor alongside panel assignments.
- Includes Conflict of Interest prevention to avoid assigning a team's own mentor as its evaluator.
- Stored in `review_panels` and `panel_faculty`.

### 6. Review Sheets & Marks
- Multi-phase evaluations: **Review 1**, **Review 2**, and **Final Review**.
- Configurable rubrics criteria with maximum marks (Problem Statement, Methodology, Implementation/Demo, Viva & Presentation).
- Panel faculty grading interface with criteria scoring, feedback remarks, and automatic score calculation.
- Stored in `reviews`, `review_criteria`, `team_reviews`, and `review_marks`.

### 7. Downloadable Reports (Excel & PDF)
One-click generation of downloadable reports in both **Excel (.xlsx)** and **PDF (.pdf)** formats for:
1. Student Roster (Grade A & Grade B — displaying student names only)
2. Team Formations & Student Members (with `25ITP...` Team IDs)
3. Faculty Details & Areas of Specialization
4. Review Panels & Faculty Allocations (with Mentors)
5. Review Marks & Evaluation Scores
6. Database SQL Backup Dump

### 8. Database Tools & Clean Reset
- `schema.sql` / `database.sql`: Clean database DDL script with no dummy student or faculty data.
- Database SQL Backup: Export complete database dump.
- Database SQL Restore: Upload and execute SQL backup.
- Clean Reset: Clear all data rows while keeping schema structure intact for fresh entries.

---

## 🗄️ MySQL Database Schema

The database `smart_miniproject_db` consists of 13 core relational tables:
1. `users` — Authentication credentials and role-based access (`admin`, `mentor`, `faculty`).
2. `students` — Student details and grade category (`Grade A`, `Grade B`).
3. `faculty` — Faculty names, unique IDs (`FAC001`), and specializations.
4. `teams` — Team details, strength, and Team IDs (`25ITP001`).
5. `team_members` — Students assigned to teams and leader designation.
6. `mentor_allocations` — Faculty mentors assigned to teams.
7. `mentor_meetings` — Pre-review meeting dates, status, feedback, and improvements.
8. `review_panels` — Review panel details and venues.
9. `panel_faculty` — Faculty assigned to panels with roles (Chairperson, Member).
10. `reviews` — Review milestones, weightages, and maximum marks.
11. `review_criteria` — Evaluation criteria with maximum marks.
12. `team_reviews` — Teams scheduled for review at panels.
13. `review_marks` — Criteria marks and evaluator feedback.

---

## 🚀 How to Run the Application

### Prerequisites
- Python 3.10+
- MySQL Server (e.g. XAMPP MySQL running on port 3306)

### Running on Windows
1. Double-click `run.bat` OR run via terminal:
   ```powershell
   python app.py
   ```
2. Open your web browser and visit:
   ```
   http://localhost:5000
   ```

### Default Credentials
- **Username:** `admin`
- **Password:** `password123` (or `admin123`)
- You can also use the **Role Switcher** in the top navigation bar to seamlessly preview the **Admin View**, **Mentor View**, and **Faculty View**.
