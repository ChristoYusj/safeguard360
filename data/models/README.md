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
|- construction-safety.pt    PPE detector checkpoint (YOLOv8 .pt export)
`- models/
   `- buffalo_l/             InsightFace model bundle
```

## What each model is used for

- `construction-safety.pt`
  PPE object detection for helmet and vest compliance. Train or export it from
  the Roboflow `construction-safety-gsnvb` dataset (see `.env.example`); the
  detector maps the Hardhat / Safety Vest classes and ignores the negative
  `NO-*` classes.
- `models/buffalo_l/`
  InsightFace / ArcFace face-recognition assets (downloaded by InsightFace on
  first use when absent)
- `backend/app/inference/models/face_landmarker.task` (outside this folder)
  MediaPipe Face Landmarker used by the driver monitor. Not committed either:
  the backend downloads it from Google's model bucket on first use with a 30 s
  timeout and refuses to load it unless its SHA-256 matches the pinned digest
  in `backend/app/inference/driver.py`.

## Configuration

The runtime reads these through the root `.env`:

- `MODELS_DIR=./data/models`
- `PPE_MODEL=construction-safety.pt`
- `FACE_MODEL=buffalo_l`

`PPE_MODEL` must match the actual filename you placed in `data/models/` (or be
an explicit path). If the file is missing, the PPE detector reports itself
unavailable and the gate falls back to face recognition only.

## If you are setting the project up on a new machine

1. Create or keep the `data/models/` folder.
2. Place the PPE model `.pt` file inside it.
3. Place the InsightFace model bundle under `data/models/models/buffalo_l/`.
4. Confirm the `.env` values match the actual local filenames.

Without these files, the frontend can still load, but the full local-first
safety runtime cannot perform recognition and PPE detection correctly.
