# SafeGuard 360 System Flow

This document explains what happens at runtime, step by step. The focus is not
just on *which component exists*, but on *how the system behaves from input to
output* and *why it is designed that way*.

## High-Level Runtime Flow

```text
Camera Source
  -> Camera Manager
  -> Active Runtime (Gate or Fleet)
  -> Local state / DB / events
  -> WebSocket + REST output
  -> Browser UI
```

The key design principle is to keep capture and inference local, then broadcast
the resulting state to the frontend.

## Attendance Workflow

This is the main gate workflow from camera frame to attendance decision.

### 1. Camera capture

The shared camera manager opens the selected source and keeps the newest raw
frame available. This is done centrally so the project does not create multiple
competing camera sessions.

### 2. Gate runtime consumes the latest frame

When Attendance mode is active, the gate runtime pulls the newest frame. It can
skip stale intermediate frames, because in a live system current state is more
important than processing every frame in sequence.

### 3. Face quality and identification

The gate runtime checks whether the frame contains a usable face:

- size and visibility
- image quality
- candidate match against enrolled workers

This stage exists so the system does not commit attendance decisions on weak or
ambiguous inputs.

### 4. PPE evaluation

If the frame is relevant for entry logic, the PPE detector checks whether
helmet and vest expectations are satisfied. The result becomes part of the live
gate state and influences whether the system can auto-approve the action.

### 5. Decision path

At this point the system chooses between:

- automatic check-in
- automatic checkout
- already checked in
- all registered workers on site
- not on site for exit mode
- review required
- unknown face

This decision stage is important because the project is not just detecting; it
is translating detection into operator-facing workflow outcomes.

### 6. Persistence and broadcast

If the decision creates or changes operational state, the backend may:

- write an attendance record
- create a review item
- store a snapshot path
- emit an event

It then broadcasts updated live status through the websocket layer so the UI
changes immediately.

## PPE Review Workflow

The PPE path becomes more interesting when the system cannot safely auto-accept
the result.

### 1. PPE creates uncertainty or non-compliance

This can happen because:

- required gear appears missing
- the PPE result is uncertain
- the policy requires manual review

### 2. Review item is created

Instead of silently failing or logging a misleading attendance record, the
backend creates a gate review entry. This gives the operator a controlled
decision point.

### 3. Review queue appears in the live feed area

The frontend shows the review inside the Attendance experience so the operator
can resolve it without switching contexts.

### 4. Operator decision

- `Accept`
  resolves the review and logs attendance if that action is allowed
- `Deny`
  resolves the review without logging attendance

### 5. Outcome placement

The project separates *live control* from *recorded outcome*:

- the PPE Command Center is only for current live mode/status
- the Workforce Roster shows the recorded PPE result attached to the worker
- completed attendance cycles later appear in Logs

This design keeps the command center from becoming a mixed live/history panel.

## Fleet Workflow

Fleet Monitoring follows the same overall architecture, but the runtime goal is
different.

### 1. Camera capture

The shared camera manager owns the active source and feeds the latest frame to
the driver runtime.

### 2. Driver runtime consumes the latest frame

The driver path also prioritizes current state over processing every frame. In
live monitoring, responsiveness matters more than replay precision.

### 3. MediaPipe analysis

The in-process driver runtime:

- initializes MediaPipe once
- attaches to the driver face
- tracks landmarks
- computes fatigue/distraction state

The rebuilt design avoids unnecessary repeated initialization and keeps the
monitoring loop stable.

### 4. Overlay and event generation

The backend updates driver state and can emit driver events. The frontend then
renders the live overlay and operator-visible status.

This workflow proves that SafeGuard 360 is not limited to gate attendance. It
supports a second real-time vision path inside the same platform.

## Logs Workflow

Logs are where the platform proves it is not only a live-screen demo.

### 1. Active cycle in roster

When a worker checks in, the worker appears in the Workforce Roster as an
active cycle.

### 2. Checkout completes the cycle

When the same worker later checks out, the system now has both:

- `ENTRY`
- `EXIT`

### 3. Roster clears, logs retain history

The active worker card is removed from the roster because the cycle is finished.
The record remains in Logs, where completed attendance sessions are meant to
live.

This design keeps the roster focused on *who is currently in play* while Logs
answer *what already happened*.

## Authentication and Password Reset Workflow

SafeGuard 360 includes full operator access control because the dashboard is
meant for real operators, not anonymous access.

### Account request and approval

1. A user requests access through the portal.
2. Backend creates a pending operator account.
3. Backend generates signed approval links.
4. Admin approval is delivered through the configured mail path.

This makes registration part of the operational workflow rather than a hidden
manual database step.

### Sign-in

1. Operator submits email and password.
2. Backend validates credentials and account status.
3. If enabled, two-factor verification is required.
4. Backend issues access and refresh tokens.

### Password reset

1. Operator requests a password reset.
2. Backend normalizes the email and checks whether the account is reset-eligible.
3. Backend creates a signed, time-limited reset token.
4. Backend builds the reset URL using `FRONTEND_APP_URL` when configured.
5. Backend delivers the reset email through the configured mail transport.

### Delivery modes

- `resend`
  sends through the verified-domain Resend sender for real delivery
- `local`
  captures the email locally for development use

The direct reset link is not exposed in the browser by default in local mode
because that would be unsafe on a shared operator machine.

## Request/Response vs Realtime Flow

The system uses two communication styles because the information types are
different.

### REST

Use REST for:

- loading logs
- changing gate mode
- deciding a review
- signing in
- requesting password reset

REST handles deliberate actions and stable record retrieval.

### WebSocket

Use websocket for:

- live preview frames
- gate state
- driver state
- event notifications

Websocket handles changing operational state.

This split keeps the frontend simple to reason about:

- ask for controlled data over REST
- listen for live runtime state over websocket

## Why The Runtime Is Designed This Way

The project makes repeated design choices in favor of local control:

- one camera owner instead of many
- local inference instead of browser inference
- local persistence instead of ephemeral live-only state
- live websocket updates instead of repeated polling for fast-changing state

Those choices make the system more suitable for industrial monitoring, where
latency, clarity, and operator response matter more than pure cloud convenience.
