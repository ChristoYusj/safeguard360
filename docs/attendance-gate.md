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

- if `all registered workers are on site`, `Check-In` is the locked boundary
  state
- if `nobody is on site`, `Check-Out` is the locked boundary state
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

The gate refuses, and it writes one `unknown_face` event to the gate event log.
Repeat attempts inside the cooldown window (30 seconds by default) are not
written again, so a person standing in front of the camera produces one record
rather than hundreds. No photograph is kept: the person is by definition not
enrolled, so storing their face would collect biometric data from someone who
never agreed to it. The record holds the time, the gate direction and the best
score that was rejected.

## Recognition Thresholds

Face recognition produces a cosine similarity between 0 and 1. The interface
shows it as a percentage, `round(score x 100)`. Four numbers decide what
happens, and all four are configuration, not constants in the code. They live
in `.env`; the shipped defaults are below.

| Setting | Default | Meaning |
| --- | --- | --- |
| `GATE_AUTO_PASS_THRESHOLD` | `0.85` | at or above this, the gate decides on its own |
| `GATE_REVIEW_THRESHOLD` | `0.79` | at or above this but below auto-pass, the match goes to the operator queue |
| `GATE_CANDIDATE_THRESHOLD` | `0.45` | at or above this, the face is named on screen as a possible match |
| `GATE_MATCH_MARGIN` | `0.10` | how far ahead of the runner-up the winner must be to be decided automatically |

The gate must also see the same worker in several consecutive recognitions
before it acts. `GATE_REQUIRED_CONFIRMATIONS` defaults to 3, which costs about
half a second at the 0.15 second recognition interval. One frame used to be
enough.

`GATE_MATCH_MARGIN` compares the winning worker against the best-scoring
*different* worker. If two people score within the margin of each other the
identification is treated as ambiguous and sent to the operator with the reason
`ambiguous_match`. It never denies entry by itself, and several enrolled photos
of one worker collapse to that worker's best score, so extra enrolment photos
do not trigger it. Enrolling the same human twice as two separate workers will.

### Face quality floors

A face has to clear four floors before it is compared against the roster at
all. The defaults are deliberately lenient: an April 2026 round of operator
feedback found that stricter values produced false "face is turned" and "too
far away" rejections at a real gate, and the recognition threshold is the real
filter. Tighten them per site.

| Setting | Default | Meaning |
| --- | --- | --- |
| `GATE_MIN_DET_SCORE` | `0.30` | detector confidence floor |
| `GATE_MIN_BLUR_SCORE` | `5.0` | Laplacian variance floor, so motion blur is tolerated |
| `GATE_MIN_FACE_AREA_RATIO` | `0.001` | the face must fill at least 0.1% of the frame |
| `GATE_MAX_YAW_OFFSET` | `inf` | how far the head may be turned; `inf` means the check is off |

### What the gate does not do

- **There is no liveness or anti-spoof check.** A printed photograph or a phone
  screen held in front of the camera is treated like a face. Do not deploy this
  at a door that matters without adding one.
- Recognition is single-camera and indoor-lit. No pose, illumination or age
  normalisation beyond what the embedding model does on its own.
- The thresholds above are engineering defaults. They have not been calibrated
  against a labelled test set, so the project publishes no true-accept or
  false-accept rate.

## Review Queue Behavior

The review queue is the operator decision point for gate cases that should not
be auto-resolved.

### Typical reasons a review appears

- face confidence is in the review band
- two enrolled workers scored too close to tell apart
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

## Feed Recovery

The camera source button has two behaviors:

- when the feed is stopped, `Refresh Sources` re-scans available camera sources
- when the feed is active, `Recover Feed` reopens the current camera and
  reconnects the live stream

If recognition mode was active before recovery, the UI restores it after the
camera starts sending stable frames again.
