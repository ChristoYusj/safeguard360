# SafeGuard 360 Architecture

## Overview

Local-first industrial safety monitoring system.

## Near-Term Build Notes

- Seed the attendance database with 2-3 real test workers for face-recognition check-in validation.
- Add PPE recognition/reference storage so compliance decisions are backed by real records.
- Keep manual override event logging in scope with worker, time, camera, and trigger metadata.

```
┌─────────────────────────────────────────────────────────────┐
│                     WINDOWS LAPTOP                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              PYTHON BACKEND (FastAPI)               │   │
│  │                                                     │   │
│  │  Camera ──► Inference ──► Decision ──► Events      │   │
│  │  Adapter    Engine       Engine       Store        │   │
│  │                                          │          │   │
│  │                              ┌───────────┴───────┐  │   │
│  │                              │    API Server     │  │   │
│  │                              │  REST + WebSocket │  │   │
│  │                              └─────────┬─────────┘  │   │
│  └────────────────────────────────────────┼────────────┘   │
│                                           │                 │
│  ┌────────────────────────────────────────▼────────────┐   │
│  │               REACT DASHBOARD (Browser)             │   │
│  │                                                     │   │
│  │   Live View │ Attendance │ Events │ Alerts │ ...   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Components

| Component        | Responsibility                      |
| ---------------- | ----------------------------------- |
| Camera Adapter   | Webcam, IP stream, video file input |
| Inference Engine | YOLO11, ArcFace, MediaPipe          |
| Decision Engine  | Business rules, alert generation    |
| Event Store      | SQLite persistence                  |
| API Server       | REST + WebSocket endpoints          |
| Actuator Adapter | Stub (future Arduino)               |
| Dashboard        | React web UI                        |

## Data Flow

1. Camera captures frame
2. Inference runs models on frame
3. Decision engine applies rules
4. Events logged to database
5. Alerts pushed via WebSocket
6. Dashboard displays real-time status

## Modes

- **Gate Mode**: Face + PPE verification
- **Driver Mode**: Fatigue + distraction monitoring
- **Idle Mode**: System paused
