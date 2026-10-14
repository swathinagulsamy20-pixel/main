import os
import pymysql
from pymysql.cursors import DictCursor
from config import Config

def get_db_connection(use_db=True):
    """Establish and return a PyMySQL connection."""
    kwargs = {
        'host': Config.DB_HOST,
        'port': Config.DB_PORT,
        'user': Config.DB_USER,
        'password': Config.DB_PASSWORD,
        'charset': 'utf8mb4',
        'cursorclass': DictCursor,
        'autocommit': False
    }
    if use_db:
        kwargs['database'] = Config.DB_NAME
    return pymysql.connect(**kwargs)

def init_db(force=False):
    """
    Ensure the MySQL database and all 13 tables are initialized from schema.sql.
    Does NOT wipe data unless force=True.
    """
    # 1. Connect without database to ensure database exists
    conn = get_db_connection(use_db=False)
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        conn.commit()
    finally:
        conn.close()

    # 2. Connect to the database and execute schema.sql
    schema_path = os.path.join(Config.BASE_DIR, 'schema.sql')
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found at {schema_path}")

    with open(schema_path, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    # Split statements carefully
    statements = []
    current_stmt = []
    for line in schema_sql.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith('--') or trimmed.startswith('/*'):
            continue
        current_stmt.append(line)
        if trimmed.endswith(';'):
            statements.append('\n'.join(current_stmt))
            current_stmt = []

    conn = get_db_connection(use_db=True)
    try:
        with conn.cursor() as cursor:
            # Disable FK checks during schema init
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            for stmt in statements:
                stmt_clean = stmt.strip()
                if stmt_clean:
                    cursor.execute(stmt_clean)
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False):
    """Execute a single query with automatic connection management."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params or ())
            result = None
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            elif commit:
                result = cursor.lastrowid
            if commit:
                conn.commit()
            return result
    except Exception as e:
        if commit:
            conn.rollback()
        raise e
    finally:
        conn.close()

def reset_all_data():
    """
    Truncate/clear all data tables while preserving database schema and users table.
    Admin user is retained.
    """
    tables = [
        'review_marks',
        'team_reviews',
        'review_criteria',
        'reviews',
        'panel_faculty',
        'review_panels',
        'mentor_meetings',
        'mentor_allocations',
        'team_members',
        'teams',
        'students',
        'faculty'
    ]
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            for table in tables:
                cursor.execute(f"TRUNCATE TABLE `{table}`;")
            # Delete non-admin users if desired, or keep faculty users cleared
            cursor.execute("DELETE FROM `users` WHERE role != 'admin';")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def backup_database():
    """
    Generate a full SQL dump string of all tables and data.
    """
    conn = get_db_connection()
    dump_lines = [
        f"-- Smart Mini Project Management System SQL Backup",
        f"-- Database: {Config.DB_NAME}",
        f"-- Host: {Config.DB_HOST}",
        f"SET FOREIGN_KEY_CHECKS = 0;\n"
    ]
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[f'Tables_in_{Config.DB_NAME}'] for row in cursor.fetchall()]
            
            for table in tables:
                # Get CREATE TABLE statement
                cursor.execute(f"SHOW CREATE TABLE `{table}`")
                create_row = cursor.fetchone()
                create_sql = create_row.get('Create Table') or list(create_row.values())[1]
                dump_lines.append(f"DROP TABLE IF EXISTS `{table}`;")
                dump_lines.append(f"{create_sql};\n")
                
                # Get data rows
                cursor.execute(f"SELECT * FROM `{table}`")
                rows = cursor.fetchall()
                if rows:
                    cols = list(rows[0].keys())
                    cols_str = ", ".join([f"`{c}`" for c in cols])
                    dump_lines.append(f"LOCK TABLES `{table}` WRITE;")
                    for r in rows:
                        vals = []
                        for c in cols:
                            v = r[c]
                            if v is None:
                                vals.append("NULL")
                            elif isinstance(v, (int, float)):
                                vals.append(str(v))
                            else:
                                escaped = pymysql.converters.escape_string(str(v))
                                vals.append(f"'{escaped}'")
                        vals_str = ", ".join(vals)
                        dump_lines.append(f"INSERT INTO `{table}` ({cols_str}) VALUES ({vals_str});")
                    dump_lines.append(f"UNLOCK TABLES;\n")
                    
        dump_lines.append("SET FOREIGN_KEY_CHECKS = 1;")
        return "\n".join(dump_lines)
    finally:
        conn.close()

def restore_database(sql_content):
    """
    Execute SQL script content to restore the database.
    """
    statements = []
    current_stmt = []
    for line in sql_content.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith('--') or trimmed.startswith('/*'):
            continue
        current_stmt.append(line)
        if trimmed.endswith(';'):
            statements.append('\n'.join(current_stmt))
            current_stmt = []

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            for stmt in statements:
                stmt_clean = stmt.strip()
                if stmt_clean:
                    cursor.execute(stmt_clean)
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
