-- ============================================================================
-- Smart Mini Project Management System - Database Schema
-- Database: smart_miniproject_db
-- Description: Automated team formation, mentor allocation, review panels,
--              evaluations, meetings, and report tracking.
-- Note: Pure Schema without sample/dummy data.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS `smart_miniproject_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `smart_miniproject_db`;

SET FOREIGN_KEY_CHECKS = 0;

-- 1. Users table (for authentication & role-based access control)
DROP TABLE IF EXISTS `review_marks`;
DROP TABLE IF EXISTS `team_reviews`;
DROP TABLE IF EXISTS `review_criteria`;
DROP TABLE IF EXISTS `reviews`;
DROP TABLE IF EXISTS `panel_faculty`;
DROP TABLE IF EXISTS `review_panels`;
DROP TABLE IF EXISTS `mentor_meetings`;
DROP TABLE IF EXISTS `mentor_allocations`;
DROP TABLE IF EXISTS `team_members`;
DROP TABLE IF EXISTS `teams`;
DROP TABLE IF EXISTS `faculty`;
DROP TABLE IF EXISTS `students`;
DROP TABLE IF EXISTS `users`;

CREATE TABLE `users` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL UNIQUE,
    `password_hash` VARCHAR(255) NOT NULL,
    `role` ENUM('admin', 'mentor', 'faculty', 'student') NOT NULL DEFAULT 'student',
    `full_name` VARCHAR(150) NOT NULL,
    `email` VARCHAR(150) NULL,
    `linked_id` VARCHAR(50) NULL COMMENT 'Student roll_number or Faculty faculty_id',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_user_role` (`role`),
    INDEX `idx_user_linked` (`linked_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Students table (student details & Grade A / Grade B category)
CREATE TABLE `students` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `roll_number` VARCHAR(50) NOT NULL UNIQUE,
    `name` VARCHAR(150) NOT NULL,
    `email` VARCHAR(150) NULL,
    `department` VARCHAR(100) DEFAULT 'Information Technology',
    `grade_category` ENUM('Grade A', 'Grade B') NOT NULL,
    `academic_year` VARCHAR(20) DEFAULT '2025-2026',
    `is_assigned` TINYINT(1) NOT NULL DEFAULT 0,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_student_grade` (`grade_category`),
    INDEX `idx_student_assigned` (`is_assigned`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Faculty table (faculty details and areas of specialization)
CREATE TABLE `faculty` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `faculty_id` VARCHAR(50) NOT NULL UNIQUE,
    `name` VARCHAR(150) NOT NULL,
    `email` VARCHAR(150) NULL,
    `department` VARCHAR(100) DEFAULT 'Information Technology',
    `specialization` VARCHAR(255) NOT NULL,
    `max_mentees` INT NOT NULL DEFAULT 5,
    `current_mentees` INT NOT NULL DEFAULT 0,
    `is_active` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_faculty_spec` (`specialization`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Teams table (formed teams and team strength)
CREATE TABLE `teams` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `team_id` VARCHAR(50) NOT NULL UNIQUE COMMENT 'Formatted e.g. 25ITP001',
    `team_name` VARCHAR(150) NULL,
    `strength` INT NOT NULL DEFAULT 4,
    `grade_a_count` INT NOT NULL DEFAULT 0,
    `grade_b_count` INT NOT NULL DEFAULT 0,
    `project_title` VARCHAR(255) NULL,
    `domain` VARCHAR(150) NULL,
    `academic_year` VARCHAR(20) DEFAULT '2025-2026',
    `status` ENUM('Formed', 'Allocated', 'Reviewing', 'Completed') DEFAULT 'Formed',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_team_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Team Members table (students assigned to teams)
CREATE TABLE `team_members` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `team_id` VARCHAR(50) NOT NULL,
    `student_id` INT NOT NULL UNIQUE,
    `roll_number` VARCHAR(50) NOT NULL,
    `is_leader` TINYINT(1) NOT NULL DEFAULT 0,
    `assigned_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`team_id`) REFERENCES `teams`(`team_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`student_id`) REFERENCES `students`(`id`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`roll_number`) REFERENCES `students`(`roll_number`) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_member_team` (`team_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Mentor Allocations table (mentors assigned to teams)
CREATE TABLE `mentor_allocations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `team_id` VARCHAR(50) NOT NULL UNIQUE,
    `faculty_id` VARCHAR(50) NOT NULL,
    `allocation_type` ENUM('Auto', 'Manual') DEFAULT 'Auto',
    `allocated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `status` ENUM('Active', 'Reassigned', 'Completed') DEFAULT 'Active',
    FOREIGN KEY (`team_id`) REFERENCES `teams`(`team_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`faculty_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_mentor_faculty` (`faculty_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Mentor Meetings table (meeting records, status, feedback & suggestions)
CREATE TABLE `mentor_meetings` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `team_id` VARCHAR(50) NOT NULL,
    `faculty_id` VARCHAR(50) NOT NULL,
    `review_stage` VARCHAR(50) NOT NULL DEFAULT 'Review 1' COMMENT 'Review 1, Review 2, Final Review',
    `meeting_date` DATE NOT NULL,
    `meeting_time` TIME NULL,
    `status` ENUM('Pending', 'Completed', 'Rescheduled', 'Missed') NOT NULL DEFAULT 'Pending',
    `feedback` TEXT NULL,
    `suggestions` TEXT NULL,
    `required_improvements` TEXT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`team_id`) REFERENCES `teams`(`team_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`faculty_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_meeting_status` (`status`),
    INDEX `idx_meeting_stage` (`review_stage`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. Review Panels table (panel details)
CREATE TABLE `review_panels` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `panel_id` VARCHAR(50) NOT NULL UNIQUE COMMENT 'Formatted e.g. PANEL-01',
    `panel_name` VARCHAR(150) NOT NULL,
    `mentor_id` VARCHAR(50) NULL COMMENT 'Assigned Panel Mentor',
    `venue` VARCHAR(150) NULL DEFAULT 'Lab / Seminar Hall',
    `description` TEXT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`mentor_id`) REFERENCES `faculty`(`faculty_id`) ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX `idx_panel_mentor` (`mentor_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. Panel Faculty table (faculty members assigned to review panels)
CREATE TABLE `panel_faculty` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `panel_id` VARCHAR(50) NOT NULL,
    `faculty_id` VARCHAR(50) NOT NULL,
    `role` ENUM('Chairperson', 'Member', 'Panel Mentor', 'Mentor', 'External Expert') DEFAULT 'Member',
    `assigned_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `unique_panel_faculty` (`panel_id`, `faculty_id`),
    FOREIGN KEY (`panel_id`) REFERENCES `review_panels`(`panel_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`faculty_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_panel_fac` (`faculty_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. Reviews table (Review 1, Review 2, Final Review definition)
CREATE TABLE `reviews` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `review_code` VARCHAR(50) NOT NULL UNIQUE COMMENT 'REV1, REV2, FINAL',
    `review_name` VARCHAR(150) NOT NULL COMMENT 'e.g. Review 1 - Problem Definition & Survey',
    `description` TEXT NULL,
    `review_date` DATE NULL,
    `max_total_marks` DECIMAL(5,2) NOT NULL DEFAULT 100.00,
    `weightage_percent` DECIMAL(5,2) NOT NULL DEFAULT 30.00,
    `status` ENUM('Draft', 'Scheduled', 'In Progress', 'Completed') DEFAULT 'Draft',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. Review Criteria table (evaluation rubrics per review)
CREATE TABLE `review_criteria` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `review_id` INT NOT NULL,
    `criteria_name` VARCHAR(150) NOT NULL,
    `max_marks` DECIMAL(5,2) NOT NULL DEFAULT 20.00,
    `description` TEXT NULL,
    `display_order` INT NOT NULL DEFAULT 1,
    FOREIGN KEY (`review_id`) REFERENCES `reviews`(`id`) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_criteria_review` (`review_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12. Team Reviews table (team scheduled for a review with a panel)
CREATE TABLE `team_reviews` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `review_id` INT NOT NULL,
    `team_id` VARCHAR(50) NOT NULL,
    `panel_id` VARCHAR(50) NOT NULL,
    `scheduled_date` DATE NULL,
    `scheduled_time` TIME NULL,
    `venue` VARCHAR(150) NULL,
    `status` ENUM('Pending', 'In Progress', 'Completed', 'Absent') DEFAULT 'Pending',
    `total_score` DECIMAL(6,2) NULL,
    `general_comments` TEXT NULL,
    `completed_at` DATETIME NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `unique_team_review` (`review_id`, `team_id`),
    FOREIGN KEY (`review_id`) REFERENCES `reviews`(`id`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`team_id`) REFERENCES `teams`(`team_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`panel_id`) REFERENCES `review_panels`(`panel_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_team_rev_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 13. Review Marks table (marks and faculty comments per criteria)
CREATE TABLE `review_marks` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `team_review_id` INT NOT NULL,
    `criteria_id` INT NOT NULL,
    `faculty_id` VARCHAR(50) NOT NULL,
    `marks_awarded` DECIMAL(5,2) NOT NULL,
    `comments` TEXT NULL,
    `submitted_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `unique_eval_mark` (`team_review_id`, `criteria_id`, `faculty_id`),
    FOREIGN KEY (`team_review_id`) REFERENCES `team_reviews`(`id`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`criteria_id`) REFERENCES `review_criteria`(`id`) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (`faculty_id`) REFERENCES `faculty`(`faculty_id`) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX `idx_mark_team_rev` (`team_review_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
