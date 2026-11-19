import os
import re
from datetime import datetime

import psycopg2
from psycopg2 import Error as PostgreSQLError
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


# =========================================================
# CONFIGURATION
# =========================================================

DATABASE_URL = os.getenv("SUPABASE_DATABASE_URL")


# =========================================================
# GET DATABASE CONNECTION
# =========================================================

def get_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "SUPABASE_DATABASE_URL is not set in the .env file."
        )

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        connect_timeout=10
    )


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def initialize_database():
    connection = get_connection()
    cursor = connection.cursor()
    # An ACTIVE row cannot survive an application restart as a live
    # attendance session. Require the user to explicitly start it again.
    cursor.execute("""
        UPDATE attendance_sessions
        SET
            status = 'ENDED',
            end_time = COALESCE(end_time, %s)
        WHERE status = 'ACTIVE'
    """, (datetime.now().strftime("%H:%M:%S"),))

    # Voice commands are data, not application code.  The seed uses stable
    # command keys so it is safe to run on every application start.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_commands (
            command_id BIGSERIAL PRIMARY KEY,
            command_key VARCHAR(80) NOT NULL UNIQUE,
            response TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # The old Action field was descriptive metadata only. Remove it from
    # existing databases as well as from the current schema.
    cursor.execute("ALTER TABLE voice_commands DROP COLUMN IF EXISTS action")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_triggers (
            trigger_id BIGSERIAL PRIMARY KEY,
            command_id BIGINT NOT NULL REFERENCES voice_commands(command_id)
                ON DELETE CASCADE,
            phrase VARCHAR(255) NOT NULL,
            normalized_phrase VARCHAR(255) NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            UNIQUE(command_id, normalized_phrase)
        )
    """)
    seed_commands = [
        ("attendance", "Attendance Mode Activating..."),
        ("hello", "Hello, this is from the database command."),
    ]
    for command_key, response in seed_commands:
        cursor.execute("""
            INSERT INTO voice_commands (command_key, response)
            VALUES (%s, %s)
            ON CONFLICT (command_key) DO NOTHING
        """, (command_key, response))

    seed_triggers = {
        "attendance": ["attendance mode", "start attendance", "begin attendance",
                       "take attendance", "mark attendance", "record attendance"],
        "hello": ["hello"],
    }
    for command_key, phrases in seed_triggers.items():
        for phrase in phrases:
            normalized = " ".join(phrase.lower().split())
            cursor.execute("""
                INSERT INTO voice_triggers (command_id, phrase, normalized_phrase)
                SELECT command_id, %s, %s FROM voice_commands
                WHERE command_key = %s
                ON CONFLICT (command_id, normalized_phrase) DO NOTHING
            """, (phrase, normalized, command_key))

    connection.commit()

    connection.close()

    print(
        "Database initialized successfully."
    )


def get_voice_commands(search=None):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        query = """
            SELECT c.command_id, c.command_key, c.response,
                   c.enabled, COALESCE(array_agg(t.phrase ORDER BY t.phrase)
                   FILTER (WHERE t.trigger_id IS NOT NULL), ARRAY[]::text[]) AS triggers
            FROM voice_commands c
            LEFT JOIN voice_triggers t ON t.command_id = c.command_id AND t.enabled
            WHERE c.enabled
            {search_clause}
            GROUP BY c.command_id
            ORDER BY c.command_id
        """.format(
            search_clause=(
                "AND (c.command_key ILIKE %s OR c.response ILIKE %s "
                "OR EXISTS (SELECT 1 FROM voice_triggers st "
                "WHERE st.command_id = c.command_id AND st.phrase ILIKE %s))"
                if search else ""
            )
        )
        params = ([f"%{search}%"] * 3) if search else []
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        connection.close()

def add_voice_command(command_key, response, phrases):
    normalized_key = "_".join(str(command_key).lower().strip().split())
    normalized_response = str(response or "").strip()
    raw_phrases = [phrases] if isinstance(phrases, str) else (phrases or [])
    phrase_pairs = [
        (str(phrase).strip(), " ".join(str(phrase).lower().split()))
        for phrase in raw_phrases if str(phrase).strip()
    ]
    if not normalized_key or not normalized_response or not phrase_pairs:
        raise ValueError("command_key, response, and at least one phrase are required")
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO voice_commands (command_key, response)
            VALUES (%s, %s)
            ON CONFLICT (command_key) DO UPDATE
            SET response = EXCLUDED.response,
                enabled = TRUE, updated_at = NOW()
            RETURNING command_id
        """, (normalized_key, normalized_response))
        command_id = cursor.fetchone()["command_id"]
        for phrase, normalized in phrase_pairs:
            cursor.execute("""
                INSERT INTO voice_triggers (command_id, phrase, normalized_phrase)
                VALUES (%s, %s, %s)
                ON CONFLICT (command_id, normalized_phrase) DO UPDATE SET enabled = TRUE
            """, (command_id, str(phrase).strip(), normalized))
        connection.commit()
        return command_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_voice_command(command_id):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM voice_commands WHERE command_id = %s", (command_id,))
        deleted = cursor.rowcount > 0
        connection.commit()
        return deleted
    finally:
        connection.close()


def list_database_schema():
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
        """)
        return cursor.fetchall()
    finally:
        connection.close()


def execute_readonly_query(sql, params=None):
    """Execute one validated SELECT statement and return JSON-friendly rows."""
    statement = str(sql).strip().rstrip(";").strip()
    if not statement or not statement.lower().startswith(("select", "with")):
        raise ValueError("Only SELECT or WITH queries are allowed")
    if ";" in statement or "--" in statement or "/*" in statement:
        raise ValueError("Only one simple read-only statement is allowed")
    if re.search(
        r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|call|do)\b",
        statement,
        flags=re.IGNORECASE,
    ):
        raise ValueError("Write or administrative SQL is not allowed")
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        allowed_tables = {row["table_name"] for row in cursor.fetchall()}
        referenced_tables = re.findall(
            r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_\.]*)(?:\s|$|,|\))",
            statement,
            flags=re.IGNORECASE,
        )
        for table in referenced_tables:
            table_name = table.split(".")[-1].strip('"')
            if table_name.lower() not in allowed_tables:
                raise ValueError(f"Table is not available for voice queries: {table_name}")
        cursor.execute(statement, params or ())
        return [dict(row) for row in cursor.fetchmany(50)]
    finally:
        connection.rollback()
        connection.close()


# =========================================================
# PROGRAMMES
# =========================================================

def get_all_programmes():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT programme_id, programme_name, created_at
        FROM programmes
        ORDER BY programme_name
    """)
    programmes = cursor.fetchall()
    connection.close()
    return programmes


def add_programme(programme_name):
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            INSERT INTO programmes (programme_name)
            VALUES (%s)
            RETURNING programme_id
        """, (programme_name,))
        programme_id = cursor.fetchone()["programme_id"]
        connection.commit()
        return programme_id
    except psycopg2.IntegrityError:
        connection.rollback()
        return None
    finally:
        connection.close()


def delete_programme(programme_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        DELETE FROM programmes
        WHERE programme_id = %s
    """, (programme_id,))
    connection.commit()
    deleted = cursor.rowcount > 0
    connection.close()
    return deleted


def update_programme(programme_id, programme_name):
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            UPDATE programmes
            SET programme_name = %s
            WHERE programme_id = %s
        """, (programme_name, programme_id))
        connection.commit()
        return cursor.rowcount > 0
    except psycopg2.IntegrityError:
        connection.rollback()
        return False
    finally:
        connection.close()


# =========================================================
# ADD STUDENT
# =========================================================
def add_student(student_id, student_name, programme_id=None):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO students (
                student_id,
                student_name,
                programme_id
            )
            VALUES (%s, %s, %s)
        """, (
            student_id,
            student_name,
            programme_id
        ))

        connection.commit()
        return True

    except psycopg2.IntegrityError:
        return False

    finally:
        connection.close()

def update_student_profile(
    student_id,
    student_name,
    programme_id=None
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE students
            SET
                student_name = %s,
                programme_id = %s
            WHERE student_id = %s
        """, (
            student_name,
            programme_id,
            student_id
        ))

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


# =========================================================
# GET STUDENT
# =========================================================

def get_student(student_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM students
        WHERE student_id = %s
    """, (
        student_id,
    ))

    student = cursor.fetchone()

    connection.close()

    return student


# =========================================================
# GET ALL STUDENTS
# =========================================================

def get_all_students():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM students
        ORDER BY student_id
    """)

    students = cursor.fetchall()

    connection.close()

    return students

# =========================================================
# GET ALL STUDENTS WITH ENROLLED CLASSES
# =========================================================

def get_all_students_with_classes():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            students.student_id,
            students.student_name,
            students.face_registered,
            students.face_folder,
            programmes.programme_id,
            programmes.programme_name,

            STRING_AGG(
                classes.class_code || ' - ' || classes.class_name,
                ', '
            ) AS classes,
            STRING_AGG(class_enrollments.class_id::TEXT, ',') AS class_ids

        FROM students

        LEFT JOIN class_enrollments
            ON students.student_id
            = class_enrollments.student_id

        LEFT JOIN classes
            ON class_enrollments.class_id
            = classes.class_id

        LEFT JOIN programmes
            ON students.programme_id = programmes.programme_id

        GROUP BY
            students.student_id,
            students.student_name,
            students.face_registered,
            students.face_folder,
            programmes.programme_id,
            programmes.programme_name

        ORDER BY
            students.student_id
    """)

    students = cursor.fetchall()

    connection.close()

    return students

# =========================================================
# STUDENT EXISTS
# =========================================================

def student_exists(student_id):

    return (
        get_student(student_id)
        is not None
    )


# =========================================================
# UPDATE FACE REGISTRATION
# =========================================================

def update_face_registration(
    student_id,
    face_folder
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE students

        SET
            face_registered = 1,
            face_folder = %s

        WHERE student_id = %s
    """, (
        face_folder,
        student_id
    ))

    connection.commit()

    updated = (
        cursor.rowcount > 0
    )

    connection.close()

    return updated


# =========================================================
# ADD CLASS / SUBJECT
# =========================================================

def add_class(
    class_code,
    class_name,
    semester=None,
    description=None,
    schedule_start=None,
    schedule_end=None,
    schedule_days=None
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO classes (
                class_code,
                class_name,
                semester,
                description,
                schedule_start,
                schedule_end,
                schedule_days
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            class_code,
            class_name,
            semester,
            description,
            schedule_start,
            schedule_end,
            schedule_days
        ))

        connection.commit()

        cursor.execute(
            "SELECT currval(pg_get_serial_sequence('classes', 'class_id')) AS class_id"
        )
        return cursor.fetchone()["class_id"]

    except psycopg2.IntegrityError:
        return None

    finally:
        connection.close()

# =========================================================
# GET CLASS BY CODE
# =========================================================

def get_class_by_code(class_code):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM classes
        WHERE class_code = %s
    """, (
        class_code,
    ))

    class_record = cursor.fetchone()

    connection.close()

    return class_record


# =========================================================
# GET CLASS BY ID
# =========================================================

def get_class_by_id(class_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM classes
        WHERE class_id = %s
    """, (
        class_id,
    ))

    class_record = cursor.fetchone()

    connection.close()

    return class_record


# =========================================================
# GET ALL CLASSES
# =========================================================

def get_all_classes():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM classes
        ORDER BY class_code
    """)

    classes = cursor.fetchall()
    connection.close()

    serialized = []
    for row in classes:
        item = dict(row)
        for key in ("created_at",):
            if hasattr(item.get(key), "isoformat"):
                item[key] = item[key].isoformat()
        for key in ("schedule_start", "schedule_end"):
            if hasattr(item.get(key), "isoformat"):
                item[key] = item[key].isoformat(timespec="minutes")
        serialized.append(item)

    return serialized

def update_class(
    class_id,
    class_code,
    class_name,
    semester=None,
    description=None,
    schedule_start=None,
    schedule_end=None,
    schedule_days=None
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE classes
            SET
                class_code = %s,
                class_name = %s,
                semester = %s,
                description = %s,
                schedule_start = %s,
                schedule_end = %s,
                schedule_days = %s
            WHERE class_id = %s
        """, (
            class_code,
            class_name,
            semester,
            description,
            schedule_start,
            schedule_end,
            schedule_days,
            class_id
        ))

        connection.commit()

        return cursor.rowcount > 0

    except psycopg2.IntegrityError:
        return False

    finally:
        connection.close()

def delete_class(class_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM classes
            WHERE class_id = %s
        """, (class_id,))

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()

def delete_student(student_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM students
            WHERE student_id = %s
        """, (student_id,))

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()
# =========================================================
# ENROLL STUDENT
# =========================================================

def enroll_student(
    class_id,
    student_id
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute("""
            INSERT INTO class_enrollments (
                class_id,
                student_id
            )
            VALUES (%s, %s)
        """, (
            class_id,
            student_id
        ))

        connection.commit()

        return True

    except psycopg2.IntegrityError:

        return False

    finally:

        connection.close()


def set_student_enrollments(student_id, class_ids):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        normalized_ids = sorted(set(int(class_id) for class_id in class_ids))
        cursor.execute(
            "DELETE FROM class_enrollments WHERE student_id = %s",
            (student_id,)
        )
        for class_id in normalized_ids:
            cursor.execute("""
                INSERT INTO class_enrollments (class_id, student_id)
                VALUES (%s, %s)
            """, (class_id, student_id))
        connection.commit()
        return True
    except (ValueError, psycopg2.IntegrityError):
        connection.rollback()
        return False
    finally:
        connection.close()


# =========================================================
# CHECK STUDENT ENROLLMENT
# =========================================================

def is_student_enrolled(
    class_id,
    student_id
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT enrollment_id

        FROM class_enrollments

        WHERE class_id = %s
        AND student_id = %s
    """, (
        class_id,
        student_id
    ))

    enrollment = cursor.fetchone()

    connection.close()

    return (
        enrollment is not None
    )


# =========================================================
# GET ENROLLED STUDENTS
# =========================================================

def get_enrolled_students(class_id):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            students.student_id,
            students.student_name,
            students.face_registered,
            students.face_folder

        FROM class_enrollments

        INNER JOIN students
            ON class_enrollments.student_id
            = students.student_id

        WHERE class_enrollments.class_id = %s

        ORDER BY students.student_id
    """, (
        class_id,
    ))

    students = cursor.fetchall()

    connection.close()

    return students


# =========================================================
# START ATTENDANCE SESSION
# =========================================================

def create_attendance_session(
    class_id,
    session_name,
    session_date,
    start_time
):

    connection = get_connection()

    cursor = connection.cursor()

    # Do not allow another ACTIVE session.
    cursor.execute("""
        SELECT session_id

        FROM attendance_sessions

        WHERE status = 'ACTIVE'

        LIMIT 1
    """)

    active_session = cursor.fetchone()

    if active_session is not None:

        connection.close()

        return None

    cursor.execute("""
        INSERT INTO attendance_sessions (
            class_id,
            session_name,
            session_date,
            start_time,
            status
        )
        VALUES (%s, %s, %s, %s, 'ACTIVE')
    """, (
        class_id,
        session_name,
        session_date,
        start_time
    ))

    connection.commit()

    cursor.execute(
        "SELECT currval(pg_get_serial_sequence('attendance_sessions', 'session_id')) AS session_id"
    )
    session_id = cursor.fetchone()["session_id"]

    connection.close()

    return session_id


# =========================================================
# GET ACTIVE ATTENDANCE SESSION
# =========================================================

def get_active_session():

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            attendance_sessions.*,

            classes.class_code,
            classes.class_name

        FROM attendance_sessions

        INNER JOIN classes
            ON attendance_sessions.class_id
            = classes.class_id

        WHERE attendance_sessions.status
            = 'ACTIVE'

        ORDER BY
            attendance_sessions.session_id DESC

        LIMIT 1
    """)

    session = cursor.fetchone()

    connection.close()

    return session


# =========================================================
# END ATTENDANCE SESSION
# =========================================================

def end_attendance_session(
    session_id,
    end_time
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        UPDATE attendance_sessions

        SET
            status = 'ENDED',
            end_time = %s

        WHERE session_id = %s
        AND status = 'ACTIVE'
    """, (
        end_time,
        session_id
    ))

    connection.commit()

    success = (
        cursor.rowcount > 0
    )

    connection.close()

    return success


# =========================================================
# CHECK ATTENDANCE
# =========================================================

def attendance_exists(
    session_id,
    student_id
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT attendance_id

        FROM attendance

        WHERE session_id = %s
        AND student_id = %s
    """, (
        session_id,
        student_id
    ))

    record = cursor.fetchone()

    connection.close()

    return (
        record is not None
    )


# =========================================================
# RECORD ATTENDANCE
# =========================================================

def record_attendance(
    session_id,
    student_id,
    attendance_date,
    attendance_time,
    similarity=None,
    track_id=None
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute("""
            INSERT INTO attendance (
                session_id,
                student_id,
                attendance_date,
                attendance_time,
                status,
                recognition_similarity,
                track_id
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                'Present',
                %s,
                %s
            )
        """, (
            session_id,
            student_id,
            attendance_date,
            attendance_time,
            similarity,
            track_id
        ))

        connection.commit()

        return True

    except psycopg2.IntegrityError:

        return False

    finally:

        connection.close()


# =========================================================
# GET ATTENDANCE FOR SESSION
# =========================================================

def get_session_attendance(
    session_id
):

    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            attendance.attendance_id,

            students.student_id,
            students.student_name,

            attendance.attendance_date,
            attendance.attendance_time,
            attendance.status,

            attendance.recognition_similarity,
            attendance.track_id

        FROM attendance

        INNER JOIN students
            ON attendance.student_id
            = students.student_id

        WHERE attendance.session_id = %s

        ORDER BY
            attendance.attendance_time
    """, (
        session_id,
    ))

    records = cursor.fetchall()

    connection.close()

    return records




# =========================================================
# GET LIVE ATTENDANCE (ALL ENROLLED STUDENTS)
# =========================================================

def get_live_attendance(session_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            students.student_id,
            students.student_name,

            COALESCE(attendance.status, 'Absent')
                AS status,

            attendance.attendance_time,
            attendance.recognition_similarity,
            attendance.track_id

        FROM attendance_sessions

        INNER JOIN class_enrollments
            ON attendance_sessions.class_id = class_enrollments.class_id

        INNER JOIN students
            ON class_enrollments.student_id = students.student_id

        LEFT JOIN attendance
            ON attendance.session_id = attendance_sessions.session_id
            AND attendance.student_id = students.student_id

        WHERE attendance_sessions.session_id = %s

        ORDER BY students.student_id
    """, (session_id,))

    records = cursor.fetchall()
    connection.close()

    return records


# =========================================================
# RUN DIRECTLY
# =========================================================

if __name__ == "__main__":

    initialize_database()
