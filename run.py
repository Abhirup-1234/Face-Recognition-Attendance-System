"""
FaceTrack AI — Entry Point
Run with: python run.py
"""
import sys
import signal
import logging
from pathlib import Path

# Add src/ to path so all backend modules are importable
sys.path.insert(0, str(Path(__file__).parent / "src"))

from app import create_app, socketio, startup, camera_manager
import config
import database as db

log = logging.getLogger(__name__)


def _graceful_shutdown(signum, frame):
    """Stop camera threads and close DB connections cleanly."""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else signum
    print(f"\n[FaceTrack AI] Received {sig_name} — shutting down gracefully...")

    # Stop all camera threads
    from app import camera_manager as cm
    if cm is not None:
        try:
            cm.stop_all()
            print("[FaceTrack AI] Camera threads stopped.")
        except Exception as e:
            log.warning("Error stopping cameras: %s", e)

    # Close DB connection for this thread
    try:
        db.close_db()
    except Exception:
        pass

    print("[FaceTrack AI] Shutdown complete.")
    sys.exit(0)


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    # Windows also supports SIGBREAK (Ctrl+Break)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _graceful_shutdown)

    app = create_app()
    startup(app)
    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=False,
        use_reloader=False,
    )
