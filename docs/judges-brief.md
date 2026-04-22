# SafeGuard 360: Judges Brief

## Project Summary

SafeGuard 360 is a local-first industrial safety monitoring platform that
combines gate attendance, PPE detection, fleet driver monitoring, operator
review workflows, logs, authentication, and an AI assistant into one system.
Its core engineering idea is that the browser is only the operator interface,
while the real runtime lives on the local machine that owns the camera, runs
computer-vision inference, stores operational data, and streams live state to
the frontend.

## Core Engineering Contributions

- one unified platform for attendance, PPE, fleet, logs, auth, and assistant behavior
- real-time local inference for both gate and fleet workflows
- shared camera-runtime architecture that avoids module conflicts
- operator review and logging flow that turns live detection into auditable state
- local-first design with external integrations layered on top rather than replacing the core runtime

## Technical Stack

- `Frontend`
  React + Vite
- `Backend`
  FastAPI + SQLAlchemy
- `Computer Vision`
  InsightFace / ArcFace, YOLO PPE detection, MediaPipe
- `Persistence`
  local SQLite + local media storage
- `Integrations`
  Groq chatbot, Resend email delivery

## Why The System Matters

Safety operations are often fragmented across separate tools and manual steps.
SafeGuard 360 treats them as one workflow: identify who is present, evaluate
whether they are compliant, let the operator resolve uncertain cases, preserve
history, and expose the live state through one dashboard.

## Why It Is Non-Trivial

This project is not just a dashboard UI. It coordinates multiple real-time
computer-vision pipelines, shared camera ownership, live websocket updates,
operator decision points, and local persistence inside one local-first
architecture. The non-trivial part is the system integration: making all of
those pieces behave like one product rather than unrelated demos.
