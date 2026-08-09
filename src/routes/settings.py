"""
routes/settings.py

Settings Blueprint.
"""

from flask import Blueprint, render_template

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
def settings():
    """
    System Settings page.
    """
    return render_template(
        "settings.html",
        page_title="Settings"
    )
