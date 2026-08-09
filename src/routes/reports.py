"""
routes/reports.py

Reports Blueprint.
"""

from flask import Blueprint, render_template

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reports")
def reports():
    """
    Reports page (Work In Progress).
    """
    return render_template(
        "reports.html",
        page_title="Reports"
    )
