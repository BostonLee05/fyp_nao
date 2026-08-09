"""
routes/attendance.py

Attendance Blueprint.
"""

from datetime import datetime
from flask import Blueprint, jsonify, render_template, request

from database import (
    create_attendance_session,
    end_attendance_session,
    get_active_session,
    get_all_classes,
    get_live_attendance,
)

attendance_bp = Blueprint("attendance", __name__)


@attendance_bp.route("/attendance")
def attendance():
    return render_template("attendance.html", page_title="Attendance")


@attendance_bp.route("/api/attendance/start", methods=["POST"])
def start_attendance_session():
    if get_active_session() is not None:
        return jsonify({"success": False, "message": "An attendance session is already active."}), 409

    data = request.get_json(silent=True) or {}
    class_id = data.get("class_id")
    session_name = data.get("session_name", "Attendance Session")

    if class_id is None:
        classes = get_all_classes()
        if not classes:
            return jsonify({"success": False, "message": "No classes found."}), 400
        class_id = classes[0]["class_id"]

    now = datetime.now()

    session_id = create_attendance_session(
        class_id,
        session_name,
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S")
    )

    return jsonify({"success": True, "session_id": session_id})


@attendance_bp.route("/api/attendance/end", methods=["POST"])
def end_session():
    session = get_active_session()

    if session is None:
        return jsonify({"success": False, "message": "No active session."}), 404

    success = end_attendance_session(
        session["session_id"],
        datetime.now().strftime("%H:%M:%S")
    )

    return jsonify({"success": success})


@attendance_bp.route("/api/attendance/status")
def attendance_status():
    session = get_active_session()

    return jsonify({
        "success": True,
        "active": session is not None,
        "session": dict(session) if session else None
    })


@attendance_bp.route("/api/attendance/current")
def current_attendance():

    session = get_active_session()

    if session is None:
        return jsonify({
            "success": True,
            "records": []
        })

    records = [
        dict(row)
        for row in get_live_attendance(session["session_id"])
    ]

    total = len(records)
    present = sum(1 for r in records if r["status"] == "Present")
    absent = total - present

    return jsonify({
        "success": True,
        "session": dict(session),
        "records": records,
        "statistics": {
            "total": total,
            "present": present,
            "absent": absent,
            "attendance_rate": round((present / total) * 100, 1) if total else 0
        }
    })