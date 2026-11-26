"""
routes/behaviour.py

Behaviour Analysis Blueprint.
"""

from flask import Blueprint, jsonify, render_template

from integrated_monitoring import monitor
from routes.vision import vision_system

behaviour_bp = Blueprint("behaviour", __name__)


@behaviour_bp.route("/behaviour")
def behaviour():
    return render_template(
        "behaviour.html",
        page_title="Behaviour Analysis"
    )


@behaviour_bp.route("/api/behaviour/status")
def behaviour_status():
    records = vision_system.get_behaviour_records()
    return jsonify({
        "success": True,
        "running": monitor.is_running(),
        "records": records,
        "statistics": {
            "tracked": len(records),
            "using_phone": sum(
                1 for record in records
                if record["phone_detected"]
                or record["behaviour_code"] == "USING_PHONE"
            ),
            "alerts": sum(
                1 for record in records
                if record["severity"] != "normal"
            )
        }
    })
