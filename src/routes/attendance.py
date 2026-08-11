"""
routes/jh_attendance.py

Attendance Blueprint.
"""

from datetime import datetime

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request
)

from database import (
    create_attendance_session,
    end_attendance_session,
    get_active_session,
    get_all_classes,
    get_live_attendance,
)


attendance_bp = Blueprint(
    "attendance",
    __name__
)


# =========================================================
# ATTENDANCE PAGE
# =========================================================

@attendance_bp.route("/attendance")
def attendance():

    return render_template(
        "attendance.html",
        page_title="Attendance"
    )


# =========================================================
# GET AVAILABLE SUBJECTS / CLASSES
# =========================================================

@attendance_bp.route(
    "/api/attendance/classes"
)
def attendance_classes():

    classes = [
        dict(row)
        for row in get_all_classes()
    ]

    return jsonify({
        "success": True,
        "classes": classes
    })


# =========================================================
# START ATTENDANCE SESSION
# =========================================================

@attendance_bp.route(
    "/api/attendance/start",
    methods=["POST"]
)
def start_attendance_session():

    # -----------------------------------------------------
    # Check if another session is already active
    # -----------------------------------------------------

    if get_active_session() is not None:

        return jsonify({
            "success": False,
            "message": (
                "An attendance session is already active."
            )
        }), 409

    # -----------------------------------------------------
    # Get request data
    # -----------------------------------------------------

    data = request.get_json(
        silent=True
    ) or {}

    class_id = data.get("class_id")

    session_date = data.get(
        "session_date"
    )

    session_name = data.get(
        "session_name",
        "Attendance Session"
    )

    # -----------------------------------------------------
    # Validate subject
    # -----------------------------------------------------

    if class_id is None:

        return jsonify({
            "success": False,
            "message": "Please select a subject."
        }), 400

    try:

        class_id = int(class_id)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "Invalid subject selected."
        }), 400

    # -----------------------------------------------------
    # Validate date
    # -----------------------------------------------------

    if not session_date:

        return jsonify({
            "success": False,
            "message": (
                "Please select an attendance date."
            )
        }), 400

    # -----------------------------------------------------
    # Validate date format
    # -----------------------------------------------------

    try:

        datetime.strptime(
            session_date,
            "%Y-%m-%d"
        )

    except ValueError:

        return jsonify({
            "success": False,
            "message": "Invalid attendance date."
        }), 400

    # -----------------------------------------------------
    # Get current start time
    # -----------------------------------------------------

    now = datetime.now()

    start_time = now.strftime(
        "%H:%M:%S"
    )

    # -----------------------------------------------------
    # Create attendance session
    # -----------------------------------------------------

    session_id = create_attendance_session(
        class_id,
        session_name,
        session_date,
        start_time
    )

    # -----------------------------------------------------
    # Check session creation
    # -----------------------------------------------------

    if session_id is None:

        return jsonify({
            "success": False,
            "message": (
                "Unable to start attendance session."
            )
        }), 500

    # -----------------------------------------------------
    # Success
    # -----------------------------------------------------

    return jsonify({
        "success": True,
        "message": (
            "Attendance session started."
        ),
        "session_id": session_id
    })


# =========================================================
# END ATTENDANCE SESSION
# =========================================================

@attendance_bp.route(
    "/api/attendance/end",
    methods=["POST"]
)
def end_session():

    session = get_active_session()

    if session is None:

        return jsonify({
            "success": False,
            "message": "No active session."
        }), 404

    success = end_attendance_session(
        session["session_id"],
        datetime.now().strftime(
            "%H:%M:%S"
        )
    )

    return jsonify({
        "success": success,
        "message": (
            "Attendance session ended."
            if success
            else "Unable to end attendance session."
        )
    })


# =========================================================
# ATTENDANCE SESSION STATUS
# =========================================================

@attendance_bp.route(
    "/api/attendance/status"
)
def attendance_status():

    session = get_active_session()

    return jsonify({
        "success": True,
        "active": session is not None,
        "session": (
            dict(session)
            if session
            else None
        )
    })


# =========================================================
# CURRENT LIVE ATTENDANCE
# =========================================================

@attendance_bp.route(
    "/api/attendance/current"
)
def current_attendance():

    session = get_active_session()

    # -----------------------------------------------------
    # No active session
    # -----------------------------------------------------

    if session is None:

        return jsonify({
            "success": True,
            "records": [],
            "statistics": {
                "total": 0,
                "present": 0,
                "absent": 0,
                "attendance_rate": 0
            }
        })

    # -----------------------------------------------------
    # Get attendance records
    # -----------------------------------------------------

    records = [
        dict(row)
        for row in get_live_attendance(
            session["session_id"]
        )
    ]

    # -----------------------------------------------------
    # Calculate statistics
    # -----------------------------------------------------

    total = len(records)

    present = sum(
        1
        for r in records
        if r["status"] == "Present"
    )

    absent = total - present

    attendance_rate = (
        round(
            (present / total) * 100,
            1
        )
        if total
        else 0
    )

    # -----------------------------------------------------
    # Return data
    # -----------------------------------------------------

    return jsonify({
        "success": True,
        "session": dict(session),
        "records": records,
        "statistics": {
            "total": total,
            "present": present,
            "absent": absent,
            "attendance_rate": attendance_rate
        }
    })