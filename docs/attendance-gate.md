# Attendance and Gate Operations

This document describes the current Attendance behavior in the app.

## Live Gate Modes

The Attendance page operates around two direction modes:

- `Check-In` (`ENTRY`)
- `Check-Out` (`EXIT`)

The frontend can switch modes manually, and it also applies automatic mode
switching for the selected shift roster:

- when all registered workers for the shift are on site, the page switches to
  `Check-Out`
- when nobody from the shift is on site, it switches back to `Check-In`

The backend allows this mode change while the feed is still running.

## Recognition Behavior

The live gate feed uses:

- face quality checks
- enrolled-worker matching
- PPE evaluation when PPE monitoring or enforcement is active

Live recognition outcomes include:

- recognized worker
- possible match
- already checked in
- not on site for exit mode
- review required
- unknown face

## Review Queue

The review queue is for known workers who need operator approval.

Typical review triggers:

- face confidence fell into the review band
- PPE enforcement blocked automatic approval
- PPE status was uncertain

Operator actions:

- `Accept`: approves the review and logs attendance
- `Deny`: keeps the worker out and resolves the review without attendance

The review queue is displayed inside the live feed area rather than as a
separate full-width panel.

## PPE Behavior

The PPE Command Center is now limited to:

- live scan status
- mode switching between `Off`, `Monitor`, and `Enforce`

Resolved PPE findings no longer live there. Instead:

- active PPE status is shown during the live gate scan
- registered PPE findings are attached to the worker card in the Workforce
  Roster
- worker cards show a compact PPE summary in the check-in section

Current worker-card PPE presentation:

- `Compliant` for clear scans
- `Flagged` when PPE issues were recorded
- small red badges for missing required items such as `Missing helmet` and
  `Missing vest`

The roster intentionally hides review timestamps and override wording in that
compact PPE summary.

## Attendance Logging Rules

### Check-In

- a worker can be automatically checked in when the match is strong enough and
  PPE rules allow it
- if the worker is already on site, the feed reports `already checked in`
  instead of creating a duplicate entry

### Check-Out

- exit mode narrows candidates to workers currently on site
- approved exit reviews write a real checkout attendance record
- completed checkout data appears in the worker roster under `Check-Out`

## Roster Display

The Workforce Roster is the long-lived operator view of what happened.

Each worker card can show:

- latest check-in details
- latest check-out details
- face match confidence
- source camera
- log method
- compact PPE summary for the check-in record

This keeps the PPE Command Center focused on live operation and the roster
focused on recorded outcomes.
