# Attendance Upgrade Backlog

Implementation rule for this track:
- Finish one feature in two passes before moving to the next feature.

Current feature:
- [x] Pass 1: multi-image and short-video enrollment for a worker
- [x] Pass 2: quality filtering, duplicate suppression, and compact representative embeddings

Next upgrades:
- [x] Cache enrolled worker embeddings in memory so gate matching does not query SQLite on every detection cycle
- [x] Add explicit check-in and check-out logic with duplicate suppression rules by direction and shift
- [x] Add shift-aware attendance state so workers show expected, on-site, late, or checked-out correctly
- [x] Add enrollment editing so more photos or a fresh video can be appended to an existing worker profile
- [ ] Add gate recognition smoothing using short track memory instead of only same-ID frame streaks
- [ ] Add face quality gates for runtime matching: minimum face size, blur threshold, side-angle tolerance
- [ ] Add unknown-person event logging and review queue
- [ ] Add attendance audit snapshots for successful and failed matches
- [ ] Add worker roster sync so Settings worker records and backend enrolled persons are no longer separate stores
- [ ] Add entry/exit camera direction support if a second gate camera is introduced
- [ ] Add operator tools to reprocess a worker's enrollment media after threshold/model changes
- [ ] Add tests for enrollment payload generation, video frame sampling, duplicate suppression, and attendance write rules
