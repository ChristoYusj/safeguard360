# Model Files

This folder is the local home for the runtime model assets used by SafeGuard
360.

If you browse the repository on GitHub, this folder will usually look almost
empty. That is expected. The actual model weights are intentionally not stored
in GitHub.

## Why the real model files are missing from GitHub

The project keeps these files local because they are:

- runtime dependencies, not source code
- relatively large
- tied to the local machine environment
- better treated as deployment assets than version-controlled code

GitHub therefore only keeps:

- this documentation file
- `.gitkeep` so the folder exists in the repo

## Expected local structure

The local machine running the full platform should have a structure like:

```text
data/models/
|- ppe-hansung.pt            PPE detector model used by the current demo setup
`- models/
   `- buffalo_l/             InsightFace model bundle
```

## What each model is used for

- `ppe-hansung.pt`
  PPE object detection for helmet and vest compliance
- `models/buffalo_l/`
  InsightFace / ArcFace face-recognition assets

## Configuration

The runtime reads these through the root `.env`:

- `MODELS_DIR=./data/models`
- `PPE_MODEL=ppe-hansung.pt`
- `FACE_MODEL=buffalo_l`

`PPE_MODEL` may also be set to a different filename or explicit path if you
replace the PPE detector model.

## If you are setting the project up on a new machine

1. Create or keep the `data/models/` folder.
2. Place the PPE model `.pt` file inside it.
3. Place the InsightFace model bundle under `data/models/models/buffalo_l/`.
4. Confirm the `.env` values match the actual local filenames.

Without these files, the frontend can still load, but the full local-first
safety runtime cannot perform recognition and PPE detection correctly.
