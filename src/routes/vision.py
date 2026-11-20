"""
routes/vision.py

Vision Monitoring Blueprint.
"""

from flask import Blueprint, Response, jsonify, render_template, stream_with_context

from database import get_active_session
from integrated_monitoring import monitor
from vision import VisionSystem

vision_bp = Blueprint("vision", __name__)

vision_system = VisionSystem()


def _process_frame(frame):
    current_session = get_active_session()
    return vision_system.process(frame, current_session=current_session)


@vision_bp.route("/vision")
def vision():
    return render_template("vision.html", page_title="Vision Monitoring")


@vision_bp.route("/api/vision/start", methods=["POST"])
def start_vision():
    try:
        monitor.set_frame_processor(_process_frame)
        monitor.start()
        return jsonify({
            "success": True,
            "message": "Vision stream started.",
            "status": monitor.get_status(),
            "vision": vision_system.get_statistics(),
        })
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc),
            "status": monitor.get_status(),
            "vision": vision_system.get_statistics(),
        }), 500


@vision_bp.route("/api/vision/stop", methods=["POST"])
def stop_vision():
    try:
        monitor.stop()
        return jsonify({
            "success": True,
            "message": "Vision stream stopped.",
            "status": monitor.get_status(),
            "vision": vision_system.get_statistics(),
        })
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": str(exc),
            "status": monitor.get_status(),
            "vision": vision_system.get_statistics(),
        }), 500


@vision_bp.route("/api/vision/status")
def vision_status():
    return jsonify({
        "success": True,
        "status": monitor.get_status(),
        "vision": vision_system.get_statistics(),
    })


@vision_bp.route("/video_feed")
def video_feed():
    if not monitor.is_running():
        return jsonify({
            "success": False,
            "message": "Vision stream is not running."
        }), 409

    return Response(
        stream_with_context(monitor.mjpeg_stream()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )