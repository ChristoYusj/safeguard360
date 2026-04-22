# SafeGuard 360 — Architecture

Local-first industrial safety monitoring system. All inference runs on the
host machine. Only the AI chatbot reaches the network (Groq or OpenAI).

## High-Level Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                          WINDOWS HOST                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                     FASTAPI BACKEND                        │  │
│  │                                                            │  │
│  │  Camera Manager ─► Gate Detector     ─► Decision / Events  │  │
│  │    (single     )    (face + PPE)        (DB + WebSocket)   │  │
│  │        │        ─► Driver Detector                         │  │
│  │        │            (fatigue / attention)                  │  │
│  │        ▼                                                   │  │
│  │  InsightFace · YOLOv8 · MediaPipe                          │  │
│  │                                                            │  │
│  │  Chatbot Service ─► Groq / OpenAI (HTTP)                   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  SQLite (data/safeguard360.db)     data/models/  (weights)       │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                 REACT DASHBOARD (browser)                  │  │
│  │                                                            │  │
│  │  Portal · Dashboard · Attendance · Enrollment · Logs ·     │  │
│  │  Chatbot · User mgmt · Settings   (AlertFeedProvider on    │  │
│  │                                    every authed page)     │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Backend Components

| Component                  | File                                       | Responsibility                                            |
| -------------------------- | ------------------------------------------ | --------------------------------------------------------- |
| `camera_manager`           | `app/camera/manager.py`                    | Owns the single capture thread, exposes frames to workers |
| `GateAttendanceRecognizer` | `app/services/gate_attendance.py`          | Face quality gating, embedding match, PPE + shift checks |
| `PpeDetector`              | `app/inference/ppe_detector.py`            | YOLOv8 wrapper with negative-class filtering             |
| `FaceRecognizer`           | `app/inference/face_recognizer.py`         | InsightFace (ArcFace) loader + cosine similarity         |
| `DriverDetector`           | `app/inference/driver.py`                  | Fatigue, distraction, seatbelt landmarks                 |
| `chatbot.send_chat`        | `app/services/chatbot.py`                  | Groq / OpenAI proxy with provider auto-selection         |
| `/ws/events`               | `app/factory.py` + `app/api/…`             | Broadcasts driver events + attendance matches            |

## Data Stores

- **`data/safeguard360.db`** — SQLite master DB (users, persons, events,
  alerts, gate policy).
- **`data/models/`** — Inference weights. `ppe-hansung.pt` at the root;
  InsightFace weights under `models/buffalo_l/`.
- **`backend/data/faces/<person_id>/`** — Enrollment thumbnails + profile json.
- **`backend/data/attendance/<record_id>/`** — Gate snapshot jpegs per event.

Paths are resolved against the repo root (`settings.resolved_models_dir`,
`settings.resolved_database_url`) so launch CWD doesn't matter.

## Gate Flow (single camera)

1. Capture thread grabs frames at `FPS_LIMIT`.
2. `GateAttendanceRecognizer` scores faces for blur, size, and yaw offset;
   rejects with a specific guidance message.
3. Best face is matched against enrolled embeddings (cosine ≥
   `FACE_MATCH_THRESHOLD`).
4. PPE detector runs on the expanded torso ROI.
5. Shift window check (`is_within_shift`) flags off-schedule arrivals.
6. Decision is written as an `Event` + `Alert`; WebSocket pushes the live
   payload.
7. Dashboard displays the match + (on violation) flashes site-wide banner.

## Driver Flow

1. Dedicated MediaPipe pipeline runs inline in the capture thread.
2. Eye aspect ratio, head pose, and mouth open signals drive fatigue /
   distraction events.
3. Events broadcast as `driver_event` over the same `/ws/events` socket.

## Modes

- **Gate** — face + PPE verification for entry.
- **Driver** — in-cab fatigue / distraction monitoring.
- **Idle** — capture released, no inference.
