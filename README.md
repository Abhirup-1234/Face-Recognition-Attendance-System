# 👁 FaceTrack AI

**Automated face-recognition attendance system** for schools — powered by InsightFace (RetinaFace + ArcFace), Flask, and React.

Built for **Narula Public School** · Developed by Abhirup

---

## ✨ Features

| Feature | Details |
|---|---|
| **Real-time face recognition** | RetinaFace detection + ArcFace (512-d) recognition |
| **Live camera feeds** | Multi-camera support with MJPEG streaming |
| **Auto attendance marking** | Multi-frame confirmation prevents false positives |
| **Indian school class hierarchy** | Nursery → XII, streams (Sci/Com/Hum) for XI/XII, sections |
| **Enrollment via webcam or upload** | Guided capture with data augmentation (FPS sampling) |
| **PDF & Excel reports** | Branded, color-coded confidence, per-section breakdown |
| **Glassmorphism dark UI** | Aurora animations, real-time Socket.IO updates |
| **Audit logging** | All destructive actions are tracked |
| **Security** | Hashed passwords, rate-limited login, restricted CORS |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React SPA (Vite)                      │
│  Dashboard · Cameras · Enroll · Reports · Manage · Cfg  │
│                   ↕ REST + Socket.IO ↕                  │
├─────────────────────────────────────────────────────────┤
│                 Flask + Flask-SocketIO                    │
│  app.py (routes) · camera_processor.py (threads)        │
│  face_engine.py (RetinaFace+ArcFace) · database.py      │
│  enroll.py · report_generator.py · preprocessing.py     │
├─────────────────────────────────────────────────────────┤
│  SQLite (data/attendance.db)  ·  .npy embeddings         │
└─────────────────────────────────────────────────────────┘
```

### Data Flow — Attendance Marking

1. `CameraProcessor` thread reads frames → every Nth frame runs detection
2. `FaceEngine.detect()` → RetinaFace finds faces, ArcFace extracts embeddings
3. `FaceEngine.identify()` → Cosine similarity against stored mean embeddings
4. Multi-frame confirmation (`CONFIRM_FRAMES`) → prevents false positives
5. `database.mark_attendance()` → persists to SQLite
6. Socket.IO emits `attendance_marked` → Dashboard/Cameras update live

---

## 🚀 Quick Start (Windows)

### Prerequisites

- **Python 3.10+** (with pip)
- **Node.js 18+** (with npm)
- A webcam or USB camera

### 1. Clone & Install

```powershell
git clone <repo-url> FaceTrackAI
cd FaceTrackAI

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Build the frontend
cd frontend
npm install
npm run build
cd ..
```

### 2. Configure

Create a `.env` file in the project root (or edit the existing one):

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=YourSecurePassword123
```

> **Note**: On first launch, the system will:
> - Auto-generate a strong `SECRET_KEY` and save it to `.env`
> - Auto-hash your plain-text password on first login

### 3. Configure Cameras

Edit `src/config.py` to set your camera sources:

```python
# USB webcam (index 0, 1, 2...)
CAMERAS = {"CAM-101": 0}

# RTSP stream
CAMERAS = {"CAM-101": "rtsp://user:pass@192.168.1.100:554/stream"}

# Folder of images (for testing)
CAMERAS = {"CAM-101": "C:/test_images/"}
```

### 4. Run

```powershell
python run.py
```

The app opens automatically at `http://127.0.0.1:5000`.
Your LAN URL is also printed for access from other devices.

---

## 📂 Project Structure

```
FaceTrackAI/
├── run.py                    # Entry point — starts Flask + cameras
├── requirements.txt          # Python dependencies
├── settings.json             # Runtime settings (auto-generated)
├── .env                      # Secrets (auto-generated)
│
├── src/                      # Backend
│   ├── app.py                # Flask routes, auth, Socket.IO
│   ├── config.py             # Configuration
│   ├── database.py           # SQLite layer
│   ├── face_engine.py        # InsightFace (RetinaFace + ArcFace)
│   ├── camera_processor.py   # Per-camera background threads
│   ├── enroll.py             # Student enrollment pipeline
│   ├── augment.py            # Data augmentation for enrollment
│   ├── preprocessing.py      # Frame enhancement (CLAHE, gamma, denoise)
│   ├── report_generator.py   # PDF + Excel report generation
│   └── utils.py              # Shared utilities
│
├── frontend/                 # React SPA
│   ├── src/
│   │   ├── App.jsx           # Router + auth guard
│   │   ├── main.jsx          # Entry point (ErrorBoundary)
│   │   ├── index.css         # Design system (975 lines)
│   │   ├── utils.js          # Shared frontend utilities
│   │   ├── api/index.js      # API client
│   │   ├── components/       # Layout, ErrorBoundary
│   │   ├── context/          # Socket, Toast, EnrollQueue
│   │   └── pages/            # Dashboard, Cameras, Enroll, Reports, Manage, Settings
│   └── dist/                 # Built output (served by Flask)
│
├── tests/                    # Pytest suite (62 tests)
│   ├── conftest.py           # Fixtures
│   ├── test_database.py      # DB CRUD tests
│   ├── test_api.py           # API endpoint tests
│   ├── test_face_engine.py   # Embedding store + normalisation tests
│   └── test_camera.py        # Camera backend diagnostics
│
└── data/                     # Runtime data (auto-created)
    ├── attendance.db         # SQLite database
    ├── embeddings/           # .npy files per student
    ├── student_photos/       # Raw enrollment images
    ├── logs/                 # Application logs
    └── reports/              # Generated PDF/Excel reports
```

---

## ⚙️ Configuration Reference

### Runtime Settings (via Settings page or `settings.json`)

| Setting | Default | Description |
|---|---|---|
| `REC_THRESHOLD` | 0.40 | ArcFace cosine similarity cutoff for recognition |
| `DET_THRESH` | 0.50 | RetinaFace detection confidence threshold |
| `CONFIRM_FRAMES` | 3 | Consecutive frames needed before marking attendance |
| `EMBEDDINGS_PER_STUDENT` | 20 | Max embeddings stored per student (FPS-sampled) |
| `PROCESS_EVERY_N` | 5 | Run detection on every Nth frame |
| `STREAM_FPS` | 10 | MJPEG stream frame rate to browser |
| `FRAME_WIDTH` | 1280 | Camera capture width |
| `FRAME_HEIGHT` | 720 | Camera capture height |
| `ENABLE_CLAHE` | true | Contrast enhancement for low-light |
| `CLAHE_CLIP_LIMIT` | 2.5 | CLAHE aggressiveness |
| `ENABLE_DENOISE` | true | Bilateral denoising |
| `SUPER_RES_SCALE` | 2 | Upscale factor for distant faces |

### Security Settings (`.env`)

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | Auto-generated | Flask session signing key |
| `ADMIN_USERNAME` | `admin` | Login username |
| `ADMIN_PASSWORD` | (set on first run) | Hashed with werkzeug PBKDF2 |

---

## 🧪 Testing

```powershell
# Run all tests with verbose output
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ -v --cov=src --cov-report=term-missing

# Run a specific test file
python -m pytest tests/test_database.py -v
```

---

## 📊 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/login` | Authenticate (rate-limited: 5/min) |
| `GET` | `/logout` | Clear session |
| `GET` | `/api/auth/status` | Check login status |
| `GET` | `/api/stats` | Dashboard statistics |
| `GET` | `/api/students` | List enrolled students |
| `DELETE` | `/api/students/:id` | Remove a student |
| `POST` | `/api/enroll` | Enroll new student (multipart) |
| `GET` | `/api/attendance` | Get attendance records |
| `DELETE` | `/api/attendance/clear` | Clear attendance for a date |
| `DELETE` | `/api/attendance/clear_all` | Clear all attendance |
| `GET` | `/api/cameras` | Camera stats |
| `POST` | `/api/cameras/:id/start` | Start camera |
| `POST` | `/api/cameras/:id/stop` | Stop camera |
| `POST` | `/api/cameras/:id/recognition` | Toggle recognition |
| `GET` | `/api/classes` | List classes |
| `POST` | `/api/classes` | Add class |
| `DELETE` | `/api/classes/:name` | Delete class |
| `GET` | `/api/sections` | List sections |
| `POST` | `/api/sections` | Add section |
| `GET` | `/api/settings` | Get settings |
| `POST` | `/api/settings` | Save settings |
| `POST` | `/api/settings/password` | Change password |
| `GET` | `/api/audit` | Get audit log |
| `DELETE` | `/api/reset_all` | Full system reset |
| `GET` | `/reports/pdf` | Download PDF report |
| `GET` | `/reports/excel` | Download Excel report |

---

## 🔒 Security

- **Passwords**: Hashed with PBKDF2-SHA256 via Werkzeug. Plaintext passwords are auto-upgraded on first login.
- **Rate limiting**: Login endpoint limited to 5 attempts/minute.
- **CORS**: Restricted to localhost and configured origins.
- **Session**: Signed with a cryptographic SECRET_KEY (auto-generated).
- **Audit trail**: All destructive actions (delete, clear, reset) are logged with timestamp and username.

---

## 📝 Tips

- 📷 **Corner cameras**: Increase `SUPER_RES_SCALE` to 2-3×
- 🌙 **Low light**: Enable CLAHE + Denoising
- 👥 **Better accuracy**: Enroll 15+ photos per student with varied angles
- ⚡ **High CPU**: Increase `PROCESS_EVERY_N` to reduce detection frequency
- 🎯 **False positives**: Raise `REC_THRESHOLD` from 0.40 towards 0.50

---

## 📄 License

© 2026 Abhirup · All rights reserved.
Built for Narula Public School.
