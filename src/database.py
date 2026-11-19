import os
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

    connection.commit()

    connection.close()

    print(
        "Database initialized successfully."
    )


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

    return classes

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