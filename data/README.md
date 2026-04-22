# Local Runtime Data

The `data/` folder is where SafeGuard 360 keeps local runtime dependencies and
local machine state.

This directory is intentionally different from normal source-code folders:

- some contents are committed only as structure or documentation
- some contents are generated or stored locally at runtime
- some contents are intentionally excluded from GitHub

## What belongs here

- `models/`
  local model files used by PPE detection and face recognition
- `safeguard360.db`
  the local SQLite database used by the running system

## Why GitHub does not show the real model files

The repository keeps the folder structure, but the actual model weights are not
committed. They are treated as local runtime assets because they are:

- large
- environment-specific
- not normal source files
- part of the deployed machine state

See [models/README.md](models/README.md) for the exact expected structure.
