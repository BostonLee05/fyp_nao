"""
routes/home.py

Home Blueprint for the NAO Smart Classroom System.
"""

from flask import Blueprint, render_template

from robot_session import robot_session

home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def dashboard():
    """
    Main dashboard page.
    """
    return render_template(
        "home.html",
        page_title="Dashboard"
    )


@home_bp.route("/dashboard")
def dashboard_alias():
    """
    Alias for the dashboard.
    """
    return render_template(
        "home.html",
        page_title="Dashboard"
    )


@home_bp.app_context_processor
def inject_robot_status():
    """
    Make robot status available to every template automatically.

    Example in Jinja:
        {{ robot.connected }}
        {{ robot.robot_ip }}
        {{ robot.remaining }}
    """
    status = robot_session.get_status()

    return {
        "robot": {
            "connected": status.get("connected", False),
            "robot_ip": status.get("robot_ip"),
            "remaining": status.get("remaining"),
            "session_id": status.get("session_id"),
            "disconnect_reason": status.get("disconnect_reason"),
            "last_disconnect_reason": status.get("last_disconnect_reason")
        }
    }


@home_bp.errorhandler(404)
def page_not_found(error):
    """
    Custom 404 page.
    """
    return render_template(
        "404.html",
        page_title="Page Not Found"
    ), 404


@home_bp.errorhandler(500)
def internal_server_error(error):
    """
    Custom 500 page.
    """
    return render_template(
        "500.html",
        page_title="Server Error"
    ), 500
