"""
routes/subjects.py

Dynamic Subjects & Students Blueprint.
"""

import os
import shutil

from flask import Blueprint, jsonify, render_template, request

from database import (
    add_class,
    add_student,
    delete_class,
    delete_student,
    enroll_student,
    get_all_classes,
    get_all_students_with_classes,
    get_student,
    set_student_enrollments,
    update_class,
    update_face_registration,
    update_student_profile,
    get_all_programmes,
    add_programme,
    delete_programme,
)

from nao_api import get_nao_manager
from modules.face_registration import get_face_registration


subjects_bp = Blueprint("subjects", __name__)


def _validate_subject_selection(class_ids):
    if not isinstance(class_ids, list):
        return "Invalid subject selection.", None

    try:
        normalized_ids = sorted(set(int(class_id) for class_id in class_ids))
    except (TypeError, ValueError):
        return "Invalid subject selected.", None

    if not normalized_ids:
        return None, []

    selected = [
        dict(row)
        for row in get_all_classes()
        if row["class_id"] in normalized_ids
    ]

    if len(selected) != len(normalized_ids):
        return "One or more selected subjects do not exist.", None

    for index, first in enumerate(selected):
        if not first.get("schedule_start") or not first.get("schedule_end"):
            continue
        first_days = set(first.get("schedule_days") or [])
        for second in selected[index + 1:]:
            if not second.get("schedule_start") or not second.get("schedule_end"):
                continue
            common_days = first_days.intersection(set(second.get("schedule_days") or []))
            if not common_days:
                continue
            if (
                first["schedule_start"] < second["schedule_end"]
                and second["schedule_start"] < first["schedule_end"]
            ):
                return (
                    f'{first["class_code"]} clashes with {second["class_code"]}.',
                    None
                )

    return None, normalized_ids


def _refresh_vision_face_embeddings():
    """Refresh active vision recognition after a face is registered."""
    try:
        from routes.vision import vision_system
        vision_system.refresh_registered_students()
    except Exception as exc:
        print(
            f"[Face Registration] Could not refresh vision embeddings: {exc}",
            flush=True
        )


# =========================================================
# PAGE
# =========================================================

@subjects_bp.route("/subjects")
def subjects():
    return render_template(
        "subjects_students.html",
        page_title="Subjects & Students"
    )


# =========================================================
# SUBJECTS
# =========================================================

@subjects_bp.route("/api/subjects", methods=["GET"])
def list_subjects():
    return jsonify({
        "success": True,
        "subjects": get_all_classes()
    })


@subjects_bp.route("/api/subjects", methods=["POST"])
def create_subject():
    data = request.get_json(silent=True) or {}

    code = str(data.get("class_code", "")).strip()
    name = str(data.get("class_name", "")).strip()
    semester = str(data.get("semester", "")).strip() or None
    description = str(data.get("description", "")).strip() or None
    schedule_start = str(data.get("schedule_start", "")).strip() or None
    schedule_end = str(data.get("schedule_end", "")).strip() or None
    schedule_days = data.get("schedule_days", [])

    if not isinstance(schedule_days, list):
        schedule_days = []
    schedule_days = sorted(set(schedule_days))

    if bool(schedule_start) != bool(schedule_end):
        return jsonify({
            "success": False,
            "message": "Start and end times are both required."
        }), 400
    if schedule_start and schedule_end and schedule_start >= schedule_end:
        return jsonify({
            "success": False,
            "message": "End time must be after start time."
        }), 400
    if schedule_start and not schedule_days:
        return jsonify({
            "success": False,
            "message": "Select at least one weekly class day."
        }), 400

    if not code or not name:
        return jsonify({
            "success": False,
            "message": "Subject code and subject name are required."
        }), 400

    class_id = add_class(
        code,
        name,
        semester,
        description,
        schedule_start,
        schedule_end,
        schedule_days
    )

    if class_id is None:
        return jsonify({
            "success": False,
            "message": "Subject code already exists."
        }), 409

    return jsonify({
        "success": True,
        "message": "Subject created successfully.",
        "class_id": class_id
    })

@subjects_bp.route("/api/subjects/<int:class_id>", methods=["PUT"])
def edit_subject(class_id):

    data = request.get_json(silent=True) or {}

    code = str(
        data.get("class_code", "")
    ).strip()

    name = str(
        data.get("class_name", "")
    ).strip()

    semester = str(
        data.get("semester", "")
    ).strip() or None
    description = str(data.get("description", "")).strip() or None
    schedule_start = str(data.get("schedule_start", "")).strip() or None
    schedule_end = str(data.get("schedule_end", "")).strip() or None
    schedule_days = data.get("schedule_days", [])
    if not isinstance(schedule_days, list):
        schedule_days = []
    schedule_days = sorted(set(schedule_days))

    if bool(schedule_start) != bool(schedule_end):
        return jsonify({
            "success": False,
            "message": "Start and end times are both required."
        }), 400
    if schedule_start and schedule_end and schedule_start >= schedule_end:
        return jsonify({
            "success": False,
            "message": "End time must be after start time."
        }), 400
    if schedule_start and not schedule_days:
        return jsonify({
            "success": False,
            "message": "Select at least one weekly class day."
        }), 400

    if not code or not name:
        return jsonify({
            "success": False,
            "message": "Subject code and subject name are required."
        }), 400

    success = update_class(
        class_id,
        code,
        name,
        semester,
        description,
        schedule_start,
        schedule_end,
        schedule_days
    )

    if not success:
        return jsonify({
            "success": False,
            "message": "Unable to update subject. Code may already exist."
        }), 409

    return jsonify({
        "success": True,
        "message": "Subject updated successfully."
    })

@subjects_bp.route("/api/subjects/<int:class_id>", methods=["DELETE"])
def remove_subject(class_id):

    success = delete_class(class_id)

    if not success:
        return jsonify({
            "success": False,
            "message": "Subject not found."
        }), 404

    return jsonify({
        "success": True,
        "message": "Subject deleted successfully."
    })

# =========================================================
# STUDENTS
# =========================================================

@subjects_bp.route("/api/students", methods=["GET"])
def list_students():
    students = [
        dict(row)
        for row in get_all_students_with_classes()
    ]

    return jsonify({
        "success": True,
        "students": students
    })


@subjects_bp.route("/api/programmes", methods=["GET"])
def list_programmes():
    return jsonify({
        "success": True,
        "programmes": [dict(row) for row in get_all_programmes()]
    })


@subjects_bp.route("/api/programmes", methods=["POST"])
def create_programme():
    data = request.get_json(silent=True) or {}
    name = str(data.get("programme_name", "")).strip()
    if not name:
        return jsonify({
            "success": False,
            "message": "Programme name is required."
        }), 400

    programme_id = add_programme(name)
    if programme_id is None:
        return jsonify({
            "success": False,
            "message": "Programme already exists."
        }), 409

    return jsonify({
        "success": True,
        "message": "Programme created successfully.",
        "programme_id": programme_id
    })


@subjects_bp.route("/api/programmes/<int:programme_id>", methods=["DELETE"])
def remove_programme(programme_id):
    if not delete_programme(programme_id):
        return jsonify({
            "success": False,
            "message": "Programme not found."
        }), 404
    return jsonify({
        "success": True,
        "message": "Programme deleted successfully."
    })


@subjects_bp.route("/api/students", methods=["POST"])
def register_student():
    """
    Create/update the student and optionally enroll them in a subject.

    Face images are no longer uploaded through this endpoint.
    Face registration is performed by the NAO camera through
    /api/students/<student_id>/face-registration/start.
    """
    data = request.get_json(silent=True)

    if data is None:
        data = request.form

    student_id = str(data.get("student_id", "")).strip()
    student_name = str(data.get("student_name", "")).strip()
    programme_id = data.get("programme_id")
    class_id = str(data.get("class_id", "")).strip()
    class_ids = data.get("class_ids", [])

    if not student_id or not student_name:
        return jsonify({
            "success": False,
            "message": "Student ID and student name are required."
        }), 400

    if get_student(student_id) is not None:
        return jsonify({
            "success": False,
            "message": (
                "This student is already registered. "
                "Use Edit in Registered Students to manage subjects."
            )
        }), 409

    try:
        programme_id = int(programme_id) if programme_id not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid programme selected."
        }), 400

    if programme_id is not None:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT 1 FROM programmes WHERE programme_id = %s",
                (programme_id,)
            )
            if cursor.fetchone() is None:
                return jsonify({
                    "success": False,
                    "message": "Invalid programme selected."
                }), 400

    if not add_student(student_id, student_name, programme_id):
        return jsonify({
            "success": False,
            "message": "Unable to create student."
        }), 500

    # Optional subject enrollment
    if not isinstance(class_ids, list):
        class_ids = []
    if class_id and not class_ids:
        class_ids = [class_id]

    clash_error, normalized_ids = _validate_subject_selection(class_ids)
    if clash_error:
        return jsonify({
            "success": False,
            "message": clash_error
        }), 409
    if normalized_ids is not None and not set_student_enrollments(
        student_id,
        normalized_ids
    ):
        return jsonify({
            "success": False,
            "message": "Invalid subject selected."
        }), 400

    return jsonify({
        "success": True,
        "message": "Student registered successfully.",
        "student_id": student_id,
        "face_registered": False
    })

@subjects_bp.route("/api/students/<student_id>", methods=["DELETE"])
def remove_student(student_id):
    student_id = str(student_id).strip()

    if not get_student(student_id):
        return jsonify({
            "success": False,
            "message": "Student not found."
        }), 404

    dataset_folder = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "dataset",
            student_id
        )
    )

    try:
        success = delete_student(student_id)

        if not success:
            return jsonify({
                "success": False,
                "message": "Unable to delete student."
            }), 500

        # Keep the filesystem synchronized with the database.
        if os.path.isdir(dataset_folder):
            shutil.rmtree(dataset_folder)

        return jsonify({
            "success": True,
            "message": "Student and face dataset deleted successfully."
        })

    except Exception as exc:
        return jsonify({
            "success": False,
            "message": f"Unable to delete student: {exc}"
        }), 500


@subjects_bp.route("/api/students/<student_id>", methods=["PUT"])
def edit_student(student_id):

    data = request.get_json(silent=True) or {}

    student_name = str(
        data.get("student_name", "")
    ).strip()

    programme_id = data.get("programme_id")
    class_ids = data.get("class_ids", [])

    if not student_name:
        return jsonify({
            "success": False,
            "message": "Student name is required."
        }), 400

    try:
        programme_id = int(programme_id) if programme_id not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid programme selected."
        }), 400

    success = update_student_profile(
        student_id,
        student_name,
        programme_id
    )

    if not success:
        return jsonify({
            "success": False,
            "message": "Student not found."
        }), 404

    clash_error, normalized_ids = _validate_subject_selection(class_ids)
    if clash_error:
        return jsonify({
            "success": False,
            "message": clash_error
        }), 409
    if normalized_ids is None or not set_student_enrollments(
        student_id,
        normalized_ids
    ):
        return jsonify({
            "success": False,
            "message": "Unable to update subject enrollments."
        }), 400

    return jsonify({
        "success": True,
        "message": "Student updated successfully."
    })

# =========================================================
# FACE REGISTRATION - START
# =========================================================

@subjects_bp.route(
    "/api/students/<student_id>/face-registration/start",
    methods=["POST"]
)
def start_face_registration(student_id):
    student_id = str(student_id).strip()

    student = get_student(student_id)

    if student is None:
        return jsonify({
            "success": False,
            "message": "Student not found. Register the student first."
        }), 404

    manager = get_nao_manager()

    if not manager.is_connected():
        return jsonify({
            "success": False,
            "message": "NAO is not connected. Connect to the robot first."
        }), 503

    registration = get_face_registration()

    if registration.is_running():
        return jsonify({
            "success": False,
            "message": "Another face registration is already running."
        }), 409

    dataset_folder = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "dataset",
            student_id
        )
    )

    try:
        from modules.robot_services import robot_services
        speaker = robot_services.speaker
        started = registration.start(
            session=manager.get_session(),
            speaker=speaker,
            student_id=student_id,
            dataset_folder=dataset_folder,
            on_complete=lambda folder: (
                update_face_registration(student_id, folder),
                _refresh_vision_face_embeddings()
            )
        )
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": f"Unable to start face registration: {exc}"
        }), 500

    if not started:
        return jsonify({
            "success": False,
            "message": "Unable to start face registration."
        }), 500

    return jsonify({
        "success": True,
        "message": "Face registration started.",
        "student_id": student_id
    })


# =========================================================
# FACE REGISTRATION - STATUS
# =========================================================

@subjects_bp.route(
    "/api/students/<student_id>/face-registration/status"
)
def face_registration_status(student_id):
    registration = get_face_registration()

    status = registration.get_status(
        student_id=str(student_id).strip()
    )

    return jsonify({
        "success": True,
        **status
    })


# =========================================================
# FACE REGISTRATION - CANCEL
# =========================================================

@subjects_bp.route(
    "/api/students/<student_id>/face-registration/cancel",
    methods=["POST"]
)
def cancel_face_registration(student_id):
    registration = get_face_registration()

    if not registration.is_running():
        return jsonify({
            "success": False,
            "message": "No face registration is currently running."
        }), 409

    registration.cancel()

    return jsonify({
        "success": True,
        "message": "Face registration cancellation requested."
    })