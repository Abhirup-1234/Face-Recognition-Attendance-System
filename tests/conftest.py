"""
Pytest fixtures for FaceTrack AI test suite.
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path

import pytest

# Ensure src/ is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Override config paths BEFORE importing anything else
_tmp = tempfile.mkdtemp(prefix="facetrack_test_")
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass123"


@pytest.fixture(autouse=True, scope="session")
def _setup_test_dirs():
    """Create temp dirs for test data and clean up after."""
    import config
    config.DB_PATH = Path(_tmp) / "test.db"
    config.EMBEDDINGS_DIR = Path(_tmp) / "embeddings"
    config.STUDENT_IMG_DIR = Path(_tmp) / "student_photos"
    config.LOG_DIR = Path(_tmp) / "logs"
    config.REPORT_DIR = Path(_tmp) / "reports"
    config.LOG_FILE = config.LOG_DIR / "test.log"
    config.SETTINGS_FILE = Path(_tmp) / "settings.json"

    for d in [config.EMBEDDINGS_DIR, config.STUDENT_IMG_DIR,
              config.LOG_DIR, config.REPORT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    yield

    shutil.rmtree(_tmp, ignore_errors=True)


@pytest.fixture
def fresh_db():
    """Provide a fresh database for each test."""
    import config
    import database as db

    # Remove old DB if exists
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()

    # Re-init
    db.init_db()
    yield db

    # Cleanup
    db.close_db()
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()


@pytest.fixture
def app(fresh_db):
    """Create a Flask test app with a fresh database."""
    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def authed_client(client):
    """Flask test client that is already logged in."""
    client.post("/login", json={
        "username": "admin",
        "password": "testpass123",
    })
    return client
