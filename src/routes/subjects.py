"""
routes/subjects.py

Subjects & Students Blueprint.
"""

from flask import Blueprint, render_template

subjects_bp = Blueprint("subjects", __name__)


@subjects_bp.route("/subjects")
def subjects():
    """
    Subjects & Students Management page.
    """
    return render_template(
        "subjects_students.html",
        page_title="Subjects & Students"
    )
