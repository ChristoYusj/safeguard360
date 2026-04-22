# Attendance and Gate Operations

This document describes the current Attendance and PPE behavior from the
operator's point of view. It is a behavior document, not an implementation
document.

## Gate Direction Modes

The Attendance page works with two gate directions:

- `Check-In`
  workers are arriving on site
- `Check-Out`
  workers are leaving the site

The operator switches modes manually. The UI does not auto-flip the direction
for you. Instead it applies `roster-based lock boundaries` so the operator
cannot move the system into an impossible state.

### Boundary behavior

- if `all registered workers are on site`, `Check-Out` is the locked boundary
  state
- if `nobody is on site`, `Check-In` is the locked boundary state
- if the site is in a partial state, the operator may switch manually

This keeps the workflow controlled while still preventing obviously incorrect
mode selections.

## What The Live Feed Messages Mean

The live feed can show several operator-facing outcomes.

### Recognized worker

The system matched a worker strongly enough for the current mode and can either
log attendance directly or continue through PPE/review logic.

### Already checked in

The worker is already on site during `Check-In`, so the system does not create
a duplicate entry.

### All registered workers on site

The site is already full for the selected shift and the operator should use
`Check-Out` if exit scanning is intended.

### Not on site for exit mode

The face may belong to a known worker, but that worker is not currently on site
for the purposes of checkout.

### Review required

The system has enough information to believe this is a known worker, but not
enough confidence or compliance certainty to approve the action automatically.

### Unknown face

No enrolled worker match was strong enough to treat the face as a known person.

## Review Queue Behavior

The review queue is the operator decision point for gate cases that should not
be auto-resolved.

### Typical reasons a review appears

- face confidence is in the review band
- PPE enforcement blocked automatic approval
- the PPE result is uncertain

### Operator actions

- `Accept`
  resolves the review and logs attendance when appropriate
- `Deny`
  resolves the review without writing attendance

The review queue is intentionally placed inside the live feed area, because it
belongs to the active gate workflow.

## PPE Behavior

The system separates `live PPE control` from `recorded PPE outcome`.

### PPE Command Center

This area is only for:

- the current PPE mode (`Off`, `Monitor`, `Enforce`)
- live scan status
- live gate messaging

### Workforce Roster PPE summary

Recorded PPE findings are shown in the worker card, not in the command center.
The current compact presentation is:

- `Compliant`
  required PPE was confirmed clearly enough
- `Flagged`
  PPE issues were recorded
- small red badges such as `Missing helmet` and `Missing vest`

This keeps the command center focused on current runtime status and the roster
focused on recorded worker outcomes.

## Attendance Logging Rules

### Check-In behavior

- a worker can be auto-checked in when recognition and PPE rules allow it
- duplicate check-ins are prevented
- review decisions can still produce a valid entry when accepted

### Check-Out behavior

- checkout is limited to workers currently considered on site
- approved exit reviews create a real checkout record
- checkout details appear in the worker card while the cycle is active

## Workforce Roster Behavior

The Workforce Roster shows `active attendance cycles`, not all historical
records.

Each active worker card can include:

- latest check-in details
- latest checkout details if the cycle is still active in view
- camera source
- face match confidence
- log method
- compact PPE summary

## Full Cycle Movement: Roster to Logs

One of the most important current behaviors is how a complete attendance cycle
is handled.

### While the cycle is active

After `ENTRY`, the worker remains visible in the Workforce Roster because the
system still considers that attendance cycle open.

### When the cycle completes

After the same worker also gets a valid `EXIT`:

- the active worker card is cleared from the Workforce Roster
- the completed cycle remains in Logs as part of attendance history

This is intentional:

- the roster answers `who is currently active`
- the logs answer `what already happened`

That separation keeps the live gate page readable and keeps history in the
correct place.
