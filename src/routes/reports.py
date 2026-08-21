"""
routes/reports.py

Reports Blueprint.

Provides the attendance report page and attendance
report API for a selected subject/class and date.
"""

from datetime import datetime

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request
)

from database import (
    get_all_classes,
    get_connection
)


reports_bp = Blueprint("reports", __name__)


# =========================================================
# REPORT PAGE
# =========================================================

@reports_bp.route("/reports")
def reports():
    """
    Attendance Reports page.
    """
    return render_template(
        "reports.html",
        page_title="Reports"
    )


# =========================================================
# GET SUBJECTS / CLASSES
# =========================================================

@reports_bp.route("/api/reports/classes")
def report_classes():
    """
    Return all available subjects/classes for the
    attendance report dropdown.
    """

    classes = [
        dict(row)
        for row in get_all_classes()
    ]

    return jsonify({
        "success": True,
        "classes": classes
    })


# =========================================================
# ATTENDANCE REPORT
# =========================================================

@reports_bp.route("/api/reports/attendance")
def attendance_report():
    """
    Return attendance for all students enrolled in a
    selected subject/class on a selected date.

    Students with an attendance record are Present.
    Students without an attendance record are Absent.
    """

    selected_date = request.args.get("date")
    class_id = request.args.get("class_id")

    # -----------------------------------------------------
    # Validate date
    # -----------------------------------------------------

    if not selected_date:
        return jsonify({
            "success": False,
            "message": "Please select an attendance date."
        }), 400

    try:
        selected_date_obj = datetime.strptime(
            selected_date,
            "%Y-%m-%d"
        ).date()

    except ValueError:
        return jsonify({
            "success": False,
            "message": "Invalid attendance date."
        }), 400

    # -----------------------------------------------------
    # Do not allow future dates
    # -----------------------------------------------------

    today = datetime.now().date()

    if selected_date_obj > today:
        return jsonify({
            "success": False,
            "message": "Future dates cannot be selected."
        }), 400

    # -----------------------------------------------------
    # Validate class ID
    # -----------------------------------------------------

    try:
        class_id = int(class_id)

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Please select a valid subject/class."
        }), 400

    # -----------------------------------------------------
    # Query the selected class/date
    # -----------------------------------------------------

    connection = get_connection()
    cursor = connection.cursor()

    try:

        # -------------------------------------------------
        # Get class information
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                class_id,
                class_code,
                class_name
            FROM classes
            WHERE class_id = ?
        """, (
            class_id,
        ))

        class_record = cursor.fetchone()

        if class_record is None:
            return jsonify({
                "success": False,
                "message": "Subject/class not found."
            }), 404

        # -------------------------------------------------
        # Find the attendance session for the selected date
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                session_id
            FROM attendance_sessions
            WHERE class_id = ?
            AND session_date = ?
            ORDER BY session_id DESC
            LIMIT 1
        """, (
            class_id,
            selected_date,
        ))

        session = cursor.fetchone()

        # -------------------------------------------------
        # Get ALL enrolled students.
        #
        # LEFT JOIN attendance means students with no
        # attendance record are still returned as Absent.
        # -------------------------------------------------

        if session is not None:

            session_id = session["session_id"]

            cursor.execute("""
                SELECT
                    students.student_id,
                    students.student_name,

                    COALESCE(
                        attendance.status,
                        'Absent'
                    ) AS status,

                    attendance.attendance_time

                FROM class_enrollments

                INNER JOIN students
                    ON class_enrollments.student_id
                    = students.student_id

                LEFT JOIN attendance
                    ON attendance.student_id
                    = students.student_id
                    AND attendance.session_id = ?

                WHERE class_enrollments.class_id = ?

                ORDER BY students.student_id
            """, (
                session_id,
                class_id,
            ))

        else:

            # No attendance session exists for this date.
            # Everyone enrolled in the class is therefore
            # shown as Absent for reporting purposes.

            cursor.execute("""
                SELECT
                    students.student_id,
                    students.student_name,
                    'Absent' AS status,
                    NULL AS attendance_time

                FROM class_enrollments

                INNER JOIN students
                    ON class_enrollments.student_id
                    = students.student_id

                WHERE class_enrollments.class_id = ?

                ORDER BY students.student_id
            """, (
                class_id,
            ))

        records = cursor.fetchall()

        # -------------------------------------------------
        # Summary
        # -------------------------------------------------

        total = len(records)

        present = sum(
            1
            for row in records
            if row["status"] == "Present"
        )

        absent = total - present

        rate = (
            round((present / total) * 100, 1)
            if total > 0
            else 0
        )

        return jsonify({
            "success": True,

            "date": selected_date,

            "display_date":
                selected_date_obj.strftime(
                    "%d %B %Y"
                ),

            "class": {
                "class_id": class_record["class_id"],
                "class_code": class_record["class_code"],
                "class_name": class_record["class_name"]
            },

            "session_exists":
                session is not None,

            "summary": {
                "total": total,
                "present": present,
                "absent": absent,
                "rate": rate
            },

            "records": [
                {
                    "student_id":
                        row["student_id"],

                    "student_name":
                        row["student_name"],

                    "status":
                        row["status"],

                    "attendance_time":
                        row["attendance_time"]
                }

                for row in records
            ]
        })

    finally:
        connection.close()