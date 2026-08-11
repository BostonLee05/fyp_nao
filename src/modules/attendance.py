from datetime import datetime

from database import (
    initialize_database,
    get_student,
    get_active_session,
    is_student_enrolled,
    attendance_exists,
    record_attendance
)


# =========================================================
# ATTENDANCE RESULT CODES
# =========================================================

RESULT_RECORDED = "RECORDED"
RESULT_ALREADY_RECORDED = "ALREADY_RECORDED"
RESULT_NO_ACTIVE_SESSION = "NO_ACTIVE_SESSION"
RESULT_STUDENT_NOT_FOUND = "STUDENT_NOT_FOUND"
RESULT_NOT_ENROLLED = "NOT_ENROLLED"
RESULT_FAILED = "FAILED"


# =========================================================
# MARK ATTENDANCE
# =========================================================

def mark_attendance(
    student_id,
    similarity=None,
    track_id=None
):

    # Get student
    student = get_student(student_id)

    if student is None:
        print(
            f"\nAttendance rejected: "
            f"Student ID '{student_id}' does not exist."
        )
        return RESULT_STUDENT_NOT_FOUND

    # Get active attendance session
    active_session = get_active_session()

    if active_session is None:
        print(
            "\nAttendance not recorded: "
            "There is no active attendance session."
        )
        return RESULT_NO_ACTIVE_SESSION

    session_id = active_session["session_id"]
    class_id = active_session["class_id"]

    # Check enrollment
    if not is_student_enrolled(
        class_id,
        student_id
    ):
        print(
            f"\nAttendance rejected: "
            f"{student['student_name']} "
            f"({student_id}) is not enrolled in "
            f"{active_session['class_code']} - "
            f"{active_session['class_name']}."
        )
        return RESULT_NOT_ENROLLED

    # Prevent duplicate attendance
    if attendance_exists(
        session_id,
        student_id
    ):
        return RESULT_ALREADY_RECORDED

    # Get current date and time
    now = datetime.now()

    attendance_date = active_session["session_date"]
    attendance_time = now.strftime("%H:%M:%S")

    # Record attendance
    success = record_attendance(
        session_id=session_id,
        student_id=student_id,
        attendance_date=attendance_date,
        attendance_time=attendance_time,
        similarity=similarity,
        track_id=track_id
    )

    if not success:
        return RESULT_FAILED

    print("\n" + "=" * 60)
    print("ATTENDANCE RECORDED")
    print(f"Student ID: {student['student_id']}")
    print(f"Student name: {student['student_name']}")
    print(
        f"Class: "
        f"{active_session['class_code']} - "
        f"{active_session['class_name']}"
    )
    print(f"Session: {active_session['session_name']}")
    print(f"Date: {attendance_date}")
    print(f"Time: {attendance_time}")

    if similarity is not None:
        print(
            f"Recognition similarity: "
            f"{similarity:.3f}"
        )

    if track_id is not None:
        print(f"Track ID: {track_id}")

    print("Status: Present")
    print("=" * 60)

    return RESULT_RECORDED


# =========================================================
# INITIALIZE DATABASE
# =========================================================

initialize_database()


# =========================================================
# TEST DIRECTLY
# =========================================================

if __name__ == "__main__":

    test_student_id = input(
        "Enter student ID: "
    ).strip()

    result = mark_attendance(
        test_student_id
    )

    print(f"\nResult: {result}")