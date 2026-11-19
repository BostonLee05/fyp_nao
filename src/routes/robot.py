"""
routes/robot.py
Robot API blueprint.
"""

from flask import Blueprint, jsonify, request

from modules.robot_services import robot_services
from robot_session import robot_session
from nao_api import get_nao_manager

robot_bp = Blueprint("robot", __name__, url_prefix="/api")

robot_api = get_nao_manager()


def _refresh_robot_status():
    if robot_session.is_connected() and not robot_api.is_connected():
        robot_services.stop_robot_services()
        robot_api.disconnect()
        robot_session.stop_session("Robot connection lost")

    status = robot_session.get_status()
    status["remaining"] = robot_session.formatted_remaining()
    return status


@robot_bp.route("/connect", methods=["POST"])
def connect():

    data = request.get_json(silent=True) or {}

    robot_ip = data.get("ip", "").strip()
    robot_port = int(data.get("port", 9559))
    duration = data.get("duration")

    if not robot_ip:
        return jsonify({
            "success": False,
            "message": "Robot IP is required."
        }), 400

    try:
        robot_api.connect(robot_ip, robot_port)
        robot_services.start_for_session(robot_api.get_session())

        robot_session.start_session(
            robot_ip=robot_ip,
            duration_seconds=duration
        )

        status = robot_session.get_status()
        status["remaining"] = robot_session.formatted_remaining()

        return jsonify({
            "success": True,
            "message": "Robot connected successfully.",
            "status": status
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@robot_bp.route("/disconnect", methods=["POST"])
def disconnect():

    robot_services.stop_robot_services()

    try:
        robot_api.disconnect()

    except Exception:
        pass

    robot_session.stop_session("Manual Disconnect")

    status = robot_session.get_status()
    status["remaining"] = robot_session.formatted_remaining()

    return jsonify({
        "success": True,
        "message": "Robot disconnected.",
        "status": status
    })


@robot_bp.route("/status")
def status():
    status = _refresh_robot_status()

    return jsonify({
        "success": True,
        "status": status
    })

@robot_bp.route("/session")
def session():
    status = _refresh_robot_status()

    return jsonify({
        "success": True,
        "status": status
    })

@robot_bp.route("/ping")
def ping():
    status = _refresh_robot_status()
    connected = status["connected"]

    return jsonify({
        "success": True,
        "connected": connected,
        "status": status
    })
