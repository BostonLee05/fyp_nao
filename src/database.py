import sqlite3


# =========================================================
# CONFIGURATION
# =========================================================

DATABASE_FILE = "classroom.db"


# =========================================================
# GET DATABASE CONNECTION
# =========================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE_FILE
    )

    connection.row_factory = sqlite3.Row

    # Enable foreign-key enforcement in SQLite.
    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def initialize_database():

    connection = get_connection()

    cursor = connection.cursor()

    # -----------------------------------------------------
    # STUDENTS
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (

            student_id TEXT PRIMARY KEY,

            student_name TEXT NOT NULL,

            face_registered INTEGER
                NOT NULL
                DEFAULT 0,

            face_folder TEXT,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -----------------------------------------------------
    # MIGRATE EXISTING STUDENTS TABLE
    # -----------------------------------------------------
    try:
        cursor.execute("""
            ALTER TABLE students
            ADD COLUMN programme TEXT
        """)
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise

    # -----------------------------------------------------
    # CLASSES
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classes (

            class_id INTEGER
                PRIMARY KEY AUTOINCREMENT,

            class_code TEXT
                NOT NULL
                UNIQUE,

            class_name TEXT
                NOT NULL,

            semester TEXT,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    try:
        cursor.execute("""
            ALTER TABLE classes
            ADD COLUMN semester TEXT
        """)
    except sqlite3.OperationalError:
        pass

    # -----------------------------------------------------
    # CLASS ENROLLMENTS
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS class_enrollments (

            enrollment_id INTEGER
                PRIMARY KEY AUTOINCREMENT,

            class_id INTEGER
                NOT NULL,

            student_id TEXT
                NOT NULL,

            enrolled_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (class_id)
                REFERENCES classes(class_id)
                ON DELETE CASCADE,

            FOREIGN KEY (student_id)
                REFERENCES students(student_id)
                ON DELETE CASCADE,

            UNIQUE (
                class_id,
                student_id
            )
        )
    """)

    # -----------------------------------------------------
    # ATTENDANCE SESSIONS
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_sessions (

            session_id INTEGER
                PRIMARY KEY AUTOINCREMENT,

            class_id INTEGER
                NOT NULL,

            session_name TEXT,

            session_date TEXT
                NOT NULL,

            start_time TEXT
                NOT NULL,

            end_time TEXT,

            status TEXT
                NOT NULL
                DEFAULT 'ACTIVE',

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (class_id)
                REFERENCES classes(class_id)
                ON DELETE CASCADE
        )
    """)

    # -----------------------------------------------------
    # ATTENDANCE RECORDS
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (

            attendance_id INTEGER
                PRIMARY KEY AUTOINCREMENT,

            session_id INTEGER
                NOT NULL,

            student_id TEXT
                NOT NULL,

            attendance_date TEXT
                NOT NULL,

            attendance_time TEXT
                NOT NULL,

            status TEXT
                NOT NULL
                DEFAULT 'Present',

            recognition_similarity REAL,

            track_id INTEGER,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (session_id)
                REFERENCES attendance_sessions(session_id)
                ON DELETE CASCADE,

            FOREIGN KEY (student_id)
                REFERENCES students(student_id)
                ON DELETE CASCADE,

            UNIQUE (
                session_id,
                student_id
            )
        )
    """)

    connection.commit()

    connection.close()

    print(
        "Database initialized successfully."
    )


# =========================================================
# ADD STUDENT
# =========================================================
def add_student(student_id, student_name, programme=None):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO students (
                student_id,
                student_name,
                programme
            )
            VALUES (?, ?, ?)
        """, (
            student_id,
            student_name,
            programme
        ))

        connection.commit()
        return True

    except sqlite3.IntegrityError:
        return False

    finally:
        connection.close()

def update_student_profile(
    student_id,
    student_name,
    programme=None
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE students
            SET
                student_name = ?,
                programme = ?
            WHERE student_id = ?
        """, (
            student_name,
            programme,
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
        WHERE student_id = ?
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

            GROUP_CONCAT(
                classes.class_code || ' - ' || classes.class_name,
                ', '
            ) AS classes

        FROM students

        LEFT JOIN class_enrollments
            ON students.student_id
            = class_enrollments.student_id

        LEFT JOIN classes
            ON class_enrollments.class_id
            = classes.class_id

        GROUP BY
            students.student_id,
            students.student_name,
            students.face_registered,
            students.face_folder

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
            face_folder = ?

        WHERE student_id = ?
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
    semester=None
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO classes (
                class_code,
                class_name,
                semester
            )
            VALUES (?, ?, ?)
        """, (
            class_code,
            class_name,
            semester
        ))

        connection.commit()

        return cursor.lastrowid

    except sqlite3.IntegrityError:
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
        WHERE class_code = ?
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
        WHERE class_id = ?
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
            VALUES (?, ?)
        """, (
            class_id,
            student_id
        ))

        connection.commit()

        return True

    except sqlite3.IntegrityError:

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

        WHERE class_id = ?
        AND student_id = ?
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

        WHERE class_enrollments.class_id = ?

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
        VALUES (?, ?, ?, ?, 'ACTIVE')
    """, (
        class_id,
        session_name,
        session_date,
        start_time
    ))

    connection.commit()

    session_id = cursor.lastrowid

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
            end_time = ?

        WHERE session_id = ?
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

        WHERE session_id = ?
        AND student_id = ?
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
                ?,
                ?,
                ?,
                ?,
                'Present',
                ?,
                ?
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

    except sqlite3.IntegrityError:

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

        WHERE attendance.session_id = ?

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

        WHERE attendance_sessions.session_id = ?

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