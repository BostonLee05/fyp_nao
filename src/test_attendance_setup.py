"""
Temporary attendance test setup only.

Run from the project's src folder:
    python test_attendance_setup.py

Prepares only the database data needed to test attendance.
"""

import os
from datetime import datetime

from database import (
    initialize_database,
    get_student,
    add_student,
    update_face_registration,
    get_class_by_code,
    add_class,
    enroll_student,
    is_student_enrolled,
    get_active_session,
    create_attendance_session,
)

STUDENT_ID = "S001"
STUDENT_NAME_IF_NEW = "S001 Test Student"

CLASS_CODE = "TEST001"
CLASS_NAME = "Attendance Test"
SESSION_NAME = "Attendance Test Session"


def main():
    print("\n========================================")
    print(" Attendance Test Database Setup")
    print("========================================\n")

    initialize_database()

    dataset_folder = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "dataset", STUDENT_ID)
    )

    print(f"[Dataset] Checking: {dataset_folder}")

    if not os.path.isdir(dataset_folder):
        print("[ERROR] Dataset folder was not found.")
        print(f"Expected: {dataset_folder}")
        return

    image_files = [
        name for name in os.listdir(dataset_folder)
        if name.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    print(f"[Dataset] Found {len(image_files)} image(s).")

    if not image_files:
        print("[ERROR] No JPG/JPEG/PNG images were found.")
        return

    student = get_student(STUDENT_ID)

    if student is None:
        print(f"[Student] Creating {STUDENT_ID}...")
        if not add_student(STUDENT_ID, STUDENT_NAME_IF_NEW):
            print("[ERROR] Failed to create student.")
            return
    else:
        print(
            f"[Student] Found existing student: "
            f"{student['student_id']} - {student['student_name']}"
        )

    if not update_face_registration(STUDENT_ID, dataset_folder):
        print("[ERROR] Failed to update face registration.")
        return

    print(f"[Student] Face folder: {dataset_folder}")
    print("[Student] Face registration: ENABLED")

    class_record = get_class_by_code(CLASS_CODE)

    if class_record is None:
        print(f"[Class] Creating {CLASS_CODE} - {CLASS_NAME}...")
        class_id = add_class(CLASS_CODE, CLASS_NAME)
        if class_id is None:
            print("[ERROR] Failed to create test class.")
            return
    else:
        class_id = class_record["class_id"]
        print(
            f"[Class] Found existing class: "
            f"{class_record['class_code']} - {class_record['class_name']}"
        )

    if is_student_enrolled(class_id, STUDENT_ID):
        print("[Enrollment] S001 is already enrolled.")
    else:
        print("[Enrollment] Enrolling S001 into TEST001...")
        if not enroll_student(class_id, STUDENT_ID):
            print("[ERROR] Failed to enroll student.")
            return
        print("[Enrollment] Enrollment successful.")

    active_session = get_active_session()

    if active_session is not None:
        print("\n[Session] An active session already exists:")
        print(f"  Session ID : {active_session['session_id']}")
        print(
            f"  Class      : {active_session['class_code']} - "
            f"{active_session['class_name']}"
        )
        print(f"  Session    : {active_session['session_name']}")
        print("[Session] No new session was created.")
    else:
        now = datetime.now()
        session_id = create_attendance_session(
            class_id=class_id,
            session_name=SESSION_NAME,
            session_date=now.strftime("%Y-%m-%d"),
            start_time=now.strftime("%H:%M:%S"),
        )

        if session_id is None:
            print("[ERROR] Failed to create active attendance session.")
            return

        print(f"[Session] Created ACTIVE session #{session_id}")

    print("\n========================================")
    print(" Attendance Test Setup Complete")
    print("========================================")
    print(f"Student       : {STUDENT_ID}")
    print(f"Dataset       : {dataset_folder}")
    print(f"Images        : {len(image_files)}")
    print(f"Class         : {CLASS_CODE} - {CLASS_NAME}")
    print("Enrollment    : S001 enrolled")
    print("Session       : ACTIVE")
    print("\nNow start/restart main.py, start Vision,")
    print("and stand in front of the camera.")
    print("Watch for: Loaded S001 -> IDENTITY CONFIRMED")
    print("           -> Attendance : RECORDED")
    print("========================================\n")


if __name__ == "__main__":
    main()
