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
    update_class,
    update_face_registration,
    update_student_profile,
)

from nao_api import get_nao_manager
from modules.face_registration import get_face_registration


subjects_bp = Blueprint("subjects", __name__)


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
        "subjects": [dict(row) for row in get_all_classes()]
    })


@subjects_bp.route("/api/subjects", methods=["POST"])
def create_subject():
    data = request.get_json(silent=True) or {}

    code = str(data.get("class_code", "")).strip()
    name = str(data.get("class_name", "")).strip()
    semester = str(data.get("semester", "")).strip() or None

    if not code or not name:
        return jsonify({
            "success": False,
            "message": "Subject code and subject name are required."
        }), 400

    class_id = add_class(code, name, semester)

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

    if not code or not name:
        return jsonify({
            "success": False,
            "message": "Subject code and subject name are required."
        }), 400

    success = update_class(
        class_id,
        code,
        name,
        semester
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
    programme = str(data.get("programme", "")).strip() or None
    class_id = str(data.get("class_id", "")).strip()

    if not student_id or not student_name:
        return jsonify({
            "success": False,
            "message": "Student ID and student name are required."
        }), 400

    existing = get_student(student_id)

    if existing is None:
        if not add_student(
            student_id,
            student_name,
            programme
        ):
            return jsonify({
                "success": False,
                "message": "Unable to create student."
            }), 500
    else:
        update_student_profile(
            student_id,
            student_name,
            programme
        )

    # Optional subject enrollment
    if class_id:
        try:
            class_id_int = int(class_id)
        except ValueError:
            return jsonify({
                "success": False,
                "message": "Invalid subject selected."
            }), 400

        if not enroll_student(
            class_id_int,
            student_id
        ):
            # Already enrolled is harmless.
            pass

    return jsonify({
        "success": True,
        "message": "Student details saved successfully.",
        "student_id": student_id,
        "face_registered": bool(
            existing and existing["face_registered"]
        ) if existing else False
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

    programme = str(
        data.get("programme", "")
    ).strip() or None

    if not student_name:
        return jsonify({
            "success": False,
            "message": "Student name is required."
        }), 400

    success = update_student_profile(
        student_id,
        student_name,
        programme
    )

    if not success:
        return jsonify({
            "success": False,
            "message": "Student not found."
        }), 404

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
        started = registration.start(
            session=manager.get_session(),
            speaker=None,
            student_id=student_id,
            dataset_folder=dataset_folder,
            on_complete=lambda folder: update_face_registration(
                student_id,
                folder
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