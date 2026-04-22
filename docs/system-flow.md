# SafeGuard 360 System Flow

This document focuses on runtime flow: what happens from camera frame to UI.

## High-Level Flow

```text
Camera Source
  -> Camera Manager
  -> Raw Frame Slot
     -> Preview Worker
     -> Gate Worker
     -> Fleet Worker
  -> WebSocket Broadcaster
  -> Browser UI
```

The capture loop stays lean. Preview rendering and inference happen in separate
workers so the camera device FPS is not dominated by one expensive path.

## Gate Flow

### Step 1: Capture

- the camera manager opens the selected source
- frames are read into the shared raw-frame slot
- no heavy inference work happens inside the capture loop

### Step 2: Gate worker consumes latest frame

- gate mode is active
- the worker pulls the newest frame only
- stale intermediate frames may be skipped intentionally

### Step 3: Face quality + matching

The gate recognizer performs:

- face detection
- blur / size / quality checks
- embedding generation
- similarity comparison against enrolled workers

### Step 4: PPE scan

For likely entry candidates:

- the PPE model runs on the subject region
- required items are evaluated
- missing/uncertain PPE becomes part of the live state

### Step 5: Decision path

Possible outcomes include:

- confirmed automatic entry
- review required
- already checked in
- not on site for exit mode
- unknown face

### Step 6: Persistence

Depending on outcome, the backend may create:

- `Attendance`
- `GateReview`
- `Event`
- `Alert`
- snapshot files under `backend/data/attendance/`

### Step 7: Realtime broadcast

The broadcaster emits:

- preview frame
- gate state payload
- attendance or review event payload

The UI then updates:

- live feed
- review queue
- roster state
- PPE command center status

## Attendance State Flow

### Check-In

- worker appears at gate
- system matches face
- PPE is evaluated if enabled
- entry is logged automatically or routed to review

### Check-Out

- exit mode narrows matching to workers currently on site
- checkout is logged when approved
- roster updates with latest exit record

### Direction boundaries

On the Attendance page:

- operators switch between `Check-In` and `Check-Out` manually
- when all registered workers for the selected shift are on site,
  `Check-Out` becomes the enforced boundary state
- when nobody is on site, `Check-In` becomes the enforced boundary state
- when the site is partially occupied, either direction can be selected

The backend accepts this change while the live feed is still running.

### Cycle completion

- once a worker has both an `ENTRY` and `EXIT`, that cycle is treated as
  complete
- completed cycles no longer keep a card alive in the Workforce Roster
- completed cycles remain available in the Logs page under attendance history

## PPE Flow

### Live scan status

The PPE Command Center is used for:

- current PPE mode
- live scan status
- current detector result messaging

### Recorded outcomes

Resolved PPE outcomes are shown in the Workforce Roster instead of staying in
the command center. The roster is the long-lived operator record of what
happened to each worker.

## Fleet Flow

### Step 1: Capture

- the same camera manager owns the Fleet camera session
- raw frames are published to the shared slot

### Step 2: Fleet worker consumes latest frame

- driver mode is active
- the Fleet worker pulls the latest frame on its own cadence

### Step 3: MediaPipe runtime

The driver runtime:

- initializes MediaPipe once
- tracks face landmarks
- computes fatigue/distraction signals
- updates driver state

### Step 4: Overlay + events

- preview worker renders live landmark/driver overlays
- driver events are queued
- websocket broadcaster pushes both status and events to the UI

## Websocket Flow

Primary behavior:

- send encoded preview frames
- send periodic status payloads
- attach gate state when mode is `gate`
- attach driver state when mode is `driver`
- send queued event payloads

This makes the browser a live control surface over the local runtime.

## Authentication and Email Flow

### Password reset request

- operator submits account email from the portal
- backend normalizes the address and verifies the account is reset-eligible
- backend creates a signed, one-time reset token
- backend builds the reset URL using `FRONTEND_APP_URL` when configured

### Delivery modes

- `resend`
  sends the password reset via Resend using the configured verified sender
- `local`
  captures the email under `backend/data/mail/` for local-first testing

The browser does not expose the reset URL in local mode unless
`MAIL_EXPOSE_LOCAL_RESET_LINKS=true`.

## Failure/Dependency Boundaries

### Browser-side issues affect:

- rendering
- operator controls
- presentation

They do not replace the inference runtime.

### Edge/runtime issues affect:

- camera access
- recognition
- PPE detection
- Fleet monitoring
- local persistence

These are the actual product-critical paths.

## Required Runtime Inputs

To run correctly, the system needs:

- camera access
- local `.env`
- local SQLite DB path
- PPE model file
- InsightFace model files
- Python dependencies
- Node dependencies for the dashboard

Without the models or local runtime, the UI can load but the system cannot
perform its core safety functions.
