"""
FaceTrack AI — Entry Point
Run with: python run.py
"""
import sys
from pathlib import Path

# Add src/ to path so all backend modules are importable
sys.path.insert(0, str(Path(__file__).parent / "src"))

from app import create_app, socketio, startup
import config

if __name__ == "__main__":
    app = create_app()
    startup(app)
    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=False,
        use_reloader=False,
    )
