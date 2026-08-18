"""
routes/attendance.py

Attendance Blueprint.

Handles:
- attendance sessions
- live attendance polling
- CSV export
"""

from datetime import datetime
from io import StringIO
import csv

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    Response
)

from database import (
    create_attendance_session,
    end_attendance_session,
    get_active_session,
    get_all_classes,
    get_session_attendance,
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
# GET SUBJECTS / CLASSES
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

    if get_active_session() is not None:

        return jsonify({
            "success": False,
            "message":
                "An attendance session is already active."
        }), 409


    data = (
        request.get_json(
            silent=True
        ) or {}
    )


    class_id = data.get("class_id")

    session_date = data.get("session_date")

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
            "message":
                "Please select a subject."
        }), 400


    try:

        class_id = int(
            class_id
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "success": False,
            "message":
                "Invalid subject selected."
        }), 400


    # -----------------------------------------------------
    # Validate date
    # -----------------------------------------------------

    if not session_date:

        return jsonify({
            "success": False,
            "message":
                "Please select an attendance date."
        }), 400


    try:

        selected_date = datetime.strptime(
            session_date,
            "%Y-%m-%d"
        ).date()

    except ValueError:

        return jsonify({
            "success": False,
            "message":
                "Invalid attendance date."
        }), 400


    # Attendance sessions should not be created for
    # future dates.

    today = datetime.now().date()

    if selected_date > today:

        return jsonify({
            "success": False,
            "message":
                "Future attendance dates are not allowed."
        }), 400


    # -----------------------------------------------------
    # Create session
    # -----------------------------------------------------

    now = datetime.now()

    session_id = create_attendance_session(
            class_id=class_id,
            session_name=session_name,
            session_date=session_date,
            start_time=
                now.strftime(
                    "%H:%M:%S"
                )
        )


    if session_id is None:

        return jsonify({
            "success": False,
            "message":
                "Unable to start attendance session."
        }), 400


    return jsonify({
        "success": True,
        "message":
            "Attendance session started.",
        "session_id":
            session_id
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
            "message":
                "No active attendance session."
        }), 404


    success = end_attendance_session(
        session["session_id"],
        datetime.now().strftime("%H:%M:%S")
    )


    return jsonify({
        "success":
            success,

        "message":
            "Attendance session ended."
            if success
            else
            "Unable to end attendance session."
    })


# =========================================================
# SESSION STATUS
# =========================================================

@attendance_bp.route(
    "/api/attendance/status"
)
def attendance_status():

    session = get_active_session()


    return jsonify({
        "success": True,

        "active":
            session is not None,

        "session":
            dict(session)
            if session
            else None
    })


# =========================================================
# CURRENT / LIVE ATTENDANCE
# =========================================================

@attendance_bp.route(
    "/api/attendance/current"
)
def current_attendance():

    """
    Return the attendance state for one exact session.

    The frontend passes session_id so that polling always
    reads the same attendance session that was started from
    the Attendance page.

    This avoids relying on a newly looked-up active session
    during every poll.
    """

    session_id = request.args.get(
            "session_id",
            type=int
        )


    # -----------------------------------------------------
    # If the frontend supplied a session ID, use it.
    # Otherwise fall back to the active session.
    # -----------------------------------------------------

    if session_id is None:

        session = get_active_session()

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

        session_id = session["session_id"]

    else:

        # Find the currently active session only when the
        # supplied session ID is the active one.
        session = get_active_session()

        if (
            session is None
            or session["session_id"] != session_id
        ):

            return jsonify({
                "success": False,
                "message":
                    "The selected attendance session is no longer active."
            }), 409


    # -----------------------------------------------------
    # Get ALL enrolled students for this exact session.
    # -----------------------------------------------------

    records = [
        dict(row)
        for row in get_live_attendance(
            session_id
        )
    ]


    total = len(records)

    present = sum(
        1
        for record in records
        if record.get("status") == "Present"
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


    return jsonify({

        "success":
            True,

        "session":
            dict(session),

        "records":
            records,

        "statistics": {

            "total":
                total,

            "present":
                present,

            "absent":
                absent,

            "attendance_rate":
                attendance_rate
        }
    })


# =========================================================
# EXPORT ATTENDANCE - CSV
# =========================================================

@attendance_bp.route(
    "/api/attendance/export"
)
def export_attendance():

    session_id = request.args.get(
            "session_id",
            type=int
        )


    if session_id is None:

        session = get_active_session()

        if session is None:

            return jsonify({
                "success": False,
                "message":
                    "No attendance session selected."
            }), 404

        session_id = session["session_id"]


    records = get_session_attendance(
            session_id
        )


    output = StringIO()

    writer = csv.writer(output)


    writer.writerow([
        "Student ID",
        "Student Name",
        "Attendance Date",
        "Attendance Time",
        "Status",
        "Recognition Similarity",
        "Track ID"
    ])


    for record in records:

        row = dict(record)

        writer.writerow([

            row.get(
                "student_id",
                ""
            ),

            row.get(
                "student_name",
                ""
            ),

            row.get(
                "attendance_date",
                ""
            ),

            row.get(
                "attendance_time",
                ""
            ),

            row.get(
                "status",
                ""
            ),

            row.get(
                "recognition_similarity",
                ""
            ),

            row.get(
                "track_id",
                ""
            )
        ])


    filename = f"attendance_session_{session_id}.csv"


    return Response(

        output.getvalue(),

        mimetype="text/csv",

        headers={
            "Content-Disposition":
                f'attachment; filename="{filename}"'
        }
    )