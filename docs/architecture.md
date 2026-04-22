# SafeGuard 360 Architecture

This document reflects the current shipped structure in the repo, not the
older backlog or prototype layout.

## System Overview

SafeGuard 360 is a local-first Windows deployment with:

- `backend/`: FastAPI API, camera orchestration, inference, database access,
  and WebSocket broadcasting
- `frontend/`: React dashboard for Attendance, Fleet Monitoring, Enrollment,
  Logs, Settings, and the chatbot
- `data/`: shared SQLite database and model weights
- `backend/data/`: runtime snapshots and face media

Only the chatbot reaches external services. Face recognition, PPE detection,
and Fleet MediaPipe analysis all run locally.

## Core Backend Ownership

### Camera Manager

File: `backend/app/camera/manager.py`

`CameraManager` is the single owner of live capture. It:

- opens and closes the selected camera source
- keeps one shared raw-frame slot
- runs separate worker threads for:
  - preview overlay rendering
  - gate recognition
  - Fleet driver detection
- keeps the capture loop lean so device FPS is not blocked by inference

This is the central arbitration point for Attendance and Fleet. Surrounding
systems should not open the camera independently.

### Gate Attendance

File: `backend/app/services/gate_attendance.py`

`GateAttendanceRecognizer` owns live gate state. It handles:

- face quality gating
- ArcFace embedding match against enrolled workers
- PPE evaluation and PPE review reasons
- entry vs exit planning
- pending review creation
- attendance record logging
- live overlay state for the gate preview

Gate direction mode is `ENTRY` or `EXIT`. In `EXIT`, the recognizer narrows
matching to workers currently on site.

### Fleet / Driver Runtime

Files:

- `backend/app/camera/driver_runtime.py`
- `backend/app/inference/driver.py`

Fleet MediaPipe now runs through an in-process runtime wrapper. The current
path:

- initializes the MediaPipe detector once
- keeps detector state in the driver runtime client
- lets the camera manager's driver worker pull the latest raw frame
- avoids the earlier subprocess/pipe failure path
- keeps preview rendering independent from detection latency

## Realtime Flow

File: `backend/app/factory.py`

The background frame broadcaster:

- emits the latest preview frame when a new encoded frame is ready
- emits periodic camera status payloads
- attaches driver state when mode is `driver`
- attaches gate state when mode is `gate`
- broadcasts pending `driver_event` and `attendance_match` events

All live traffic goes through `/ws/events`.

## Data Flow

### Attendance / Gate

1. Camera manager captures frames.
2. Gate worker reads the newest frame only.
3. Gate recognizer performs:
   - face detection and quality checks
   - ArcFace matching
   - PPE scan when applicable
   - attendance action planning
4. If review is needed, a `GateReview` record is created.
5. If access is granted, an `Attendance` record is written.
6. Events and live state are broadcast to the frontend.

### Fleet Monitoring

1. Camera manager captures frames.
2. Driver worker pulls the newest frame on its own cadence.
3. MediaPipe landmarks are processed in the driver runtime.
4. Fatigue/distraction state is updated.
5. Driver events and live state are broadcast to the frontend.

## Persistence

### Repo-level shared data

- `data/safeguard360.db`: master SQLite database
- `data/models/`: model directory resolved from the repo root

### Backend runtime outputs

- `backend/data/faces/<person_id>/`: enrollment media and thumbnails
- `backend/data/attendance/<record_id>/`: attendance snapshots

## Frontend Responsibilities

Primary page files live under `frontend/src/pages/`.

- `Attendance.jsx`: live gate feed, review queue, PPE command center, and
  workforce roster
- `Dashboard.jsx`: Fleet Monitoring live view and MediaPipe controls
- `Enrollment.jsx`: worker enrollment and profile media

The frontend does not own inference. It renders current backend state and sends
operator actions to the API.

## Current Documentation Map

- `README.md`: setup, run commands, and operator quick guide
- `docs/attendance-gate.md`: gate operator behavior and PPE flow
