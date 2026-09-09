# SafeGuard 360

SafeGuard 360 is a `local-first industrial safety monitoring platform` built
for an on-site machine, not a browser-only website. It combines live gate
attendance, PPE compliance checking, fleet driver monitoring, operator review
workflows, logs, and a safety assistant into one system. The browser dashboard
is the operator surface, but the real product lives in the local runtime that
owns the camera, runs the models, stores the local database, and pushes live
state to the UI.

The important idea behind the project is unification. In many real sites,
attendance, PPE enforcement, driver monitoring, operator logs, and follow-up
actions live in separate manual processes. SafeGuard 360 treats them as one
operational loop: a camera observes the site, local inference decides what is
happening, the backend records and broadcasts that state, and the frontend lets
an operator act on it immediately.

This architecture is intentional. The project uses local camera access, local
model files, local inference, and local persistence because the core use cases
are time-sensitive and operationally critical. A gate decision or a driver
fatigue event should not depend on sending raw frames to a distant cloud
service first. The platform therefore behaves more like an edge safety station
with a web dashboard than a normal hosted web app.

If a new CCE student opens this repository, the right mental model is:
`camera input -> backend runtime -> local AI inference -> database and event state -> websocket updates -> operator UI`.
Everything else in the project supports that loop.

## Why This Project Exists

Industrial safety workflows are often fragmented:

- attendance is logged manually or in a separate system
- PPE violations are spotted inconsistently
- driver monitoring is isolated from gate monitoring
- review decisions are not tied cleanly to logs and history
- operators have to look at several tools to understand one situation

SafeGuard 360 addresses that fragmentation by combining:

- `who is this person?`
- `are they compliant?`
- `should the system auto-approve or ask for review?`
- `what happened earlier today?`
- `what is happening in fleet monitoring right now?`

The result is a platform that is both real-time and auditable.

## Core Modules

### Attendance & PPE Detection

This is the gate-entry module. The system reads frames from the active camera,
detects and matches faces against enrolled workers, evaluates helmet and vest
compliance, and decides whether a worker should be checked in automatically,
routed to review, or denied. It also manages `Check-In` and `Check-Out` mode
behavior and keeps the Workforce Roster aligned with active attendance cycles.

### Fleet Monitoring

This module uses MediaPipe-based driver analysis to monitor the operator-facing
fleet feed. It tracks face and landmark state, computes fatigue or distraction
signals, and overlays the live result in the dashboard. It shares the same
overall runtime design as the gate system: the browser displays state, but the
local backend performs the work.

### Logs & Review Flow

The system does not stop at live detection. It records attendance, PPE-related
decisions, gate reviews, and other relevant events so the operator can inspect
what happened later. Completed attendance cycles leave the active roster and
remain available in Logs, which makes the platform behave like an operational
system rather than a transient demo.

### Operator Authentication

The project includes a real operator-auth flow with registration approval,
sign-in, logout, password changes, two-factor authentication, and password
reset. This matters in the project because the dashboard is meant to be used by
real operators, not anonymous viewers.

### Safety Chatbot

The chatbot is a Groq-backed assistant that sits on top of the operational
state. Its role is not to replace the safety logic, but to help an operator ask
questions about the system state in natural language. This turns the project
from a pure monitoring tool into a broader safety operations platform.

## How The System Works Together

The cleanest way to understand the project is to follow one frame from the
camera through the stack:

1. A camera frame enters the local backend through the shared camera manager.
2. The backend decides which runtime is active: gate recognition or fleet
   monitoring.
3. The correct inference path processes the newest available frame locally.
4. The backend converts that result into structured state:
   attendance decisions, PPE status, driver state, reviews, logs, or events.
5. That state is written to local persistence when needed.
6. The backend broadcasts live status and frames through the websocket layer.
7. The frontend renders the live state and lets the operator respond.

The frontend is therefore the control surface, not the inference engine. It
asks for data over HTTP, listens for live state over websocket, and presents
the result to the operator. The backend owns the runtime. The database owns the
history. The models provide the raw computer-vision intelligence.

## Why It Is Local-First

SafeGuard 360 is local-first for technical and operational reasons.

### Camera ownership

Only one process should truly own the active camera session. If multiple pages
or modules tried to access the camera independently, gate monitoring and fleet
monitoring would conflict. The backend solves this with a shared camera manager
that arbitrates camera access and feeds the active runtime.

### Local model files

The face-recognition model, PPE model, and MediaPipe runtime live on the local
machine. This avoids turning every detection request into a cloud round trip and
keeps the critical path under local control.

These files are intentionally not committed to GitHub. The repository ships the
code and folder structure, but the actual model weights remain local runtime
assets because they are large, environment-specific, and part of the deployed
machine state rather than normal source files.

### Local inference

Gate recognition, PPE checking, and fleet analysis happen where the camera is.
This reduces latency and makes the system usable even in environments where
internet connectivity is weak or where sending raw safety footage elsewhere is
undesirable.

### Local persistence

Attendance history, snapshots, enrollment media, and review state are stored
locally. That keeps the system auditable while still respecting the local-first
nature of the platform.

### Better fit for industrial workflows

This architecture is a better fit for industrial safety than a pure cloud web
app because the project is making operational decisions close to the physical
environment. The browser is important, but the site machine is the real runtime
center.

## End-to-End Example Workflow

A good way to understand the whole platform is to follow one worker through a
complete cycle:

1. A worker arrives at the gate and appears in the live feed.
2. The backend captures the newest frame and runs face quality checks.
3. If the face is good enough, the recognizer compares it against enrolled
   workers.
4. Once a likely worker is identified, PPE detection checks for helmet and
   vest compliance.
5. If confidence and PPE rules are good enough, the worker is checked in
   automatically.
6. If something is uncertain, the system creates a review item and the operator
   decides what to do.
7. The roster updates to show the worker's active attendance state and compact
   PPE summary.
8. Later, when the worker checks out, the exit record is created.
9. Once both `ENTRY` and `EXIT` exist, the active card leaves the roster and
   the completed cycle remains in Logs.

That single example already touches the camera manager, recognizer, PPE model,
review flow, persistence, websocket updates, and UI rendering.

## What Judges Should Notice

When presenting this project, the important technical points are not just that
it has multiple pages. The real engineering value is:

- `unified system design`
  Attendance, PPE, fleet monitoring, logs, auth, and assistant behavior are
  part of one platform rather than separate demos.
- `real-time local inference`
  The project performs meaningful computer-vision work on the site machine.
- `multiple CV pipelines in one runtime`
  Face recognition, PPE detection, and driver monitoring coexist in one system.
- `operator workflow completeness`
  The platform supports live decisions, review handling, logging, and history.
- `persistence and auditability`
  Results do not disappear after a live scan; they become part of an
  operational record.

## Repository Layout

```text
safeguard360/
|- backend/                  FastAPI app, inference, camera runtime, tests
|- frontend/                 React operator dashboard
|- data/                     SQLite DB and local model weights
|  `- roster-demo.csv        sample roster import file
|- docs/                     product, architecture, and presentation docs
|- .env.example              environment template
|- reset_admin_password.py   admin recovery utility
```

## Why `data/models/` Looks Empty On GitHub

If you browse the repository on GitHub, `data/models/` may appear to contain
only `.gitkeep` and documentation files. That is expected.

The actual PPE and face-recognition model weights are intentionally ignored by
Git because they are runtime dependencies, not source code. On the local demo
machine, those files live under `data/models/`, but GitHub only keeps the
folder structure and instructions.

See:

- [data/README.md](data/README.md)
- [data/models/README.md](data/models/README.md)

## Documentation Map

- [docs/architecture.md](docs/architecture.md)
  Engineering explanation of the system layers, ownership, and runtime design
- [docs/system-flow.md](docs/system-flow.md)
  End-to-end runtime workflows from camera frame to UI outcome
- [docs/attendance-gate.md](docs/attendance-gate.md)
  Operator-facing behavior of Attendance and PPE handling
- [docs/auth-email.md](docs/auth-email.md)
  Authentication, password-reset flow, and mail-delivery behavior
- [docs/demo-runbook.md](docs/demo-runbook.md)
  Live presentation order and talking points
- [docs/judges-brief.md](docs/judges-brief.md)
  High-signal summary for judges and first-time readers

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Windows host with camera access
- local model files in `data/models/`

### Environment

Create the root `.env` from the template:

```powershell
Copy-Item .env.example .env
```

Every non-secret value in the template already works. Generate the four
required secrets and paste them into `.env`, then set `ADMIN_EMAIL` and
`BOOTSTRAP_ADMIN_PASSWORD`:

```powershell
python -c "import secrets; print('JWT_ACCESS_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('JWT_REFRESH_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('JWT_APPROVAL_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('TOTP_ENCRYPTION_KEY=' + secrets.token_urlsafe(48))"
```

The backend refuses to start and names the missing keys if any of these is
blank.

Important variables:

- `DATABASE_URL`
- `MODELS_DIR`
- `PPE_MODEL`
- `FACE_MODEL`
- `FPS_LIMIT`
- `GROQ_API_KEY`
- `JWT_ACCESS_SECRET`
- `JWT_REFRESH_SECRET`
- `JWT_APPROVAL_SECRET`
- `ADMIN_EMAIL`
- `MAIL_TRANSPORT`
- `MAIL_LOCAL_OUTBOX_DIR`
- `MAIL_EXPOSE_LOCAL_RESET_LINKS`
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL`
- `FRONTEND_APP_URL`
- `TOTP_ENCRYPTION_KEY`

Email delivery modes:

- `MAIL_TRANSPORT=local`
  local-first mode; auth emails are captured locally
- `MAIL_TRANSPORT=resend`
  production mode; requires `RESEND_API_KEY` and `RESEND_FROM_EMAIL` on a
  verified Resend sending domain
- `MAIL_EXPOSE_LOCAL_RESET_LINKS=true`
  optional dev-only flag; exposes the reset link in the browser while using
  local mail capture

### Required local model assets

The repository does not include the actual model weights. You must place them
locally before the full system can run:

- PPE model:
  `data/models/<your-ppe-model>.pt`
- InsightFace weights:
  `data/models/models/buffalo_l/`

Set `PPE_MODEL` in `.env` to the exact filename you placed there. The template
uses `construction-safety.pt`, the export name for the recommended Roboflow
dataset linked in `.env.example`.

### Sample roster import

Use `data/roster-demo.csv` as the sample worker import file. It contains the
expected columns for the Settings worker import flow:

- `name`
- `employee_id`
- `shift_id`
- `is_active`

### Run backend

```powershell
cd backend
pip install -r requirements.txt
python main.py
```

Backend default origin:

- `http://127.0.0.1:8000`

### Run frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend default origin:

- `http://127.0.0.1:5173`

## Useful Commands

```powershell
# Backend tests and lint (dev tooling is not part of requirements.txt)
cd backend
pip install -r requirements-dev.txt
python -m pytest
ruff check .

# Frontend build
cd frontend
npm run build

# Frontend tests
cd frontend
npm test
```

## License and third-party licences

SafeGuard 360 is released under the **GNU Affero General Public License
v3.0** (see [LICENSE](LICENSE)). AGPL was chosen because the PPE detector
depends on [Ultralytics](https://github.com/ultralytics/ultralytics), which is
itself AGPL-3.0; a permissive licence for this repository would not change the
obligations that dependency imposes on a deployment.

Runtime components carry their own terms, which apply regardless of this
repository's licence:

| Component | Licence | Notes |
|---|---|---|
| `ultralytics` (YOLO) | AGPL-3.0 | Ultralytics states that models trained with it inherit AGPL. Commercial use without source disclosure needs an Ultralytics Enterprise licence. |
| InsightFace (`insightface`, `buffalo_l` weights) | Code MIT; pretrained model packs **non-commercial research use only** | The face-recognition weights this project uses are not licensed for commercial deployment. |
| MediaPipe (`mediapipe`, `face_landmarker.task`) | Apache-2.0 | |
| OpenCV, ONNX Runtime, FastAPI, React and the rest of `requirements.txt` / `package.json` | Permissive (Apache-2.0 / MIT / BSD) | |
| Your PPE checkpoint (`PPE_MODEL`) | Depends on the dataset and framework you trained it with | The Roboflow `construction-safety-gsnvb` dataset referenced in `.env.example` has its own terms; check them before redistributing weights. |

The PPE weights used on the original demo machine are not part of this
repository and their provenance is not documented here.

## AI assistance

This project was built with AI coding assistants (OpenAI Codex during the
original build; Anthropic Claude Code for the 2026 audit and upgrade series).
[AI_DISCLOSURE.md](AI_DISCLOSURE.md) says what they did, what the author did,
and how to read the commit history. The author reviewed and tested every
change and is responsible for the result.

## Notes

- `reset_admin_password.py` is kept as the admin recovery tool
- `data/roster-demo.csv` is the sample roster import file
- runtime outputs, caches, logs, models, and local env files are intentionally
  excluded from source control
