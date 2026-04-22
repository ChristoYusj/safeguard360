# SafeGuard 360 Architecture

This document describes SafeGuard 360 as a system, not just as a repo.

## Product Boundary

SafeGuard 360 is a local-first edge safety platform with a browser-based
operator UI.

It has two clear sides:

- the `web application side`
  UI, API calls, operator workflows, and dashboards
- the `local edge runtime side`
  camera ownership, local inference, local database, model files, and live
  event generation

This distinction matters because the system cannot be understood or deployed
correctly if it is treated like a normal stateless website.

## Deployment Shape

### Browser / UI Layer

Files:

- `frontend/src/pages/*`
- `frontend/src/services/api.js`

Responsibilities:

- render operator controls and state
- render roster, review queue, and event history
- display the live preview stream
- send operator actions to the backend
- subscribe to websocket updates

The browser does not run the face, PPE, or driver models.

### Backend / Edge Layer

Files:

- `backend/app/factory.py`
- `backend/app/api/*`
- `backend/app/camera/*`
- `backend/app/inference/*`
- `backend/app/services/*`

Responsibilities:

- own the local camera
- run gate recognition and PPE inference
- run Fleet MediaPipe analysis
- own authentication and password-reset orchestration
- store local attendance and review state
- emit live websocket frames and events
- serve the UI with current state

### Local Persistence Layer

Paths:

- `data/safeguard360.db`
- `backend/data/attendance/`
- `backend/data/faces/`
- `backend/data/mail/`

Responsibilities:

- attendance records
- worker roster / enrollment state
- snapshots and thumbnails
- gate review persistence
- event and alert history
- locally captured auth emails when local mail transport is enabled

### Model Layer

Paths:

- `data/models/ppe-hansung.pt`
- `data/models/models/buffalo_l/`

Responsibilities:

- PPE object detection
- face detection / embedding generation

These are runtime dependencies, not normal web assets.

## Ownership Map

### Camera Manager

Primary file:

- `backend/app/camera/manager.py`

Owns:

- active camera source
- raw frame slot
- preview encoding
- gate worker loop
- Fleet worker loop
- module ownership and mode switching

The camera manager is the single arbitration point between Attendance and
Fleet. It prevents independent camera access from fragmenting runtime state.

### Gate Attendance Recognizer

Primary file:

- `backend/app/services/gate_attendance.py`

Owns:

- face quality gating
- candidate matching against enrolled workers
- PPE evaluation and review-reason generation
- entry vs exit planning
- pending review lifecycle
- attendance logging decisions
- live gate overlay state

### Fleet Driver Runtime

Primary files:

- `backend/app/camera/driver_runtime.py`
- `backend/app/inference/driver.py`

Owns:

- MediaPipe detector lifecycle
- landmark extraction
- fatigue/distraction state
- driver overlay state
- emitted driver events

Current architecture keeps the MediaPipe path in-process and tied to the
backend runtime rather than a separate subprocess worker.

### Websocket Broadcaster

Primary file:

- `backend/app/factory.py`

Owns:

- preview frame broadcast
- status payload broadcast
- gate event broadcast
- driver event broadcast

This is the live bridge between the edge runtime and the browser UI.

### Auth and Mail Services

Primary files:

- `backend/app/api/auth.py`
- `backend/app/services/auth.py`
- `backend/app/services/email.py`

Own:

- operator login and session issuance
- password change and password reset token flow
- registration approval links
- mail transport selection between Resend and local capture
- sender and reset-link configuration through environment settings

## Runtime Modes

### Idle

- camera not in active inference mode
- no gate or Fleet processing

### Gate

- gate recognition worker active
- gate overlay state active
- attendance and review logic active

### Driver

- Fleet MediaPipe runtime active
- driver overlay state active
- fatigue/distraction event generation active

## Hosted Pieces Vs Local Pieces

### Pieces that could be hosted in a more normal web environment

- React frontend
- backend HTTP API
- authentication flows
- transactional email delivery via provider APIs
- settings / admin UI
- docs and static project pages
- chatbot request handling

### Pieces that are inherently local / edge-bound in the current design

- webcam access
- gate preview processing
- MediaPipe Fleet analysis
- YOLO PPE inference
- face recognition runtime
- local snapshots and face media
- local model files
- local SQLite state

That means SafeGuard 360 is best understood as an edge deployment with a web
dashboard, not a pure SaaS browser app.

## Security And Data Shape

### Source-controlled assets

- code
- docs
- config templates
- tests

### Local-only assets

- `.env`
- SQLite database
- model weights
- enrollment images
- attendance snapshots
- logs and caches

This separation is intentional because the local-only assets are environment
data, secrets, or runtime outputs.

## Related Docs

- [system-flow.md](system-flow.md)
- [attendance-gate.md](attendance-gate.md)
