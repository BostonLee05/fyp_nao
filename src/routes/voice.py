from flask import Blueprint, jsonify, render_template

from modules.voice_state import voice_state


voice_bp = Blueprint("voice", __name__, url_prefix="/api/voice")
voice_page_bp = Blueprint("voice_page", __name__)


@voice_page_bp.route("/voice")
def voice_dashboard():
    return render_template(
        "voice.html",
        page_title="Voice Recognition",
    )


@voice_bp.route("/status")
def voice_status():
    return jsonify({
        "success": True,
        "voice": voice_state.snapshot(),
    })


@voice_bp.route("/history")
def voice_history():
    snapshot = voice_state.snapshot()
    return jsonify({
        "success": True,
        "history": snapshot["history"],
    })


@voice_bp.route("/recommendations")
def voice_recommendations():
    snapshot = voice_state.snapshot()
    return jsonify({
        "success": True,
        "recommendations": snapshot["recommendations"],
        "recommendation_token": snapshot["recommendation_token"],
    })