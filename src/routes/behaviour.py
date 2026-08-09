"""
routes/behaviour.py

Behaviour Analysis Blueprint.
"""

from flask import Blueprint, render_template

behaviour_bp = Blueprint("behaviour", __name__)


@behaviour_bp.route("/behaviour")
def behaviour():
    """
    Behaviour Analysis page (Work In Progress).
    """
    return render_template(
        "behaviour.html",
        page_title="Behaviour Analysis"
    )
