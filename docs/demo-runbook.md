# SafeGuard 360 Demo Runbook

This document is the live presentation script for SafeGuard 360. It is written
to keep the presentation structured and technically meaningful.

## 1. Project Overview

### What I show

- the landing point of the project and a short summary of what SafeGuard 360 is

### What it proves

- this is a unified platform, not a collection of unrelated demos

### What to say

SafeGuard 360 is a local-first industrial safety monitoring platform. It brings
together gate attendance, PPE detection, fleet monitoring, logs, operator
authentication, and an AI assistant into one operational system.

## 2. Attendance and PPE Detection

### What I show

- the Attendance page
- live gate feed
- worker recognition
- PPE status behavior
- review queue if relevant

### What it proves

- the platform performs live local inference
- it can move from raw camera input to operator-facing decisions
- attendance and PPE are part of one workflow

### What to say

This is the gate side of the system. A live frame enters the backend, the
system matches the face against enrolled workers, evaluates PPE, and decides
whether to auto-log the worker, request operator review, or reject the action.

## 3. Workforce Roster and Logs

### What I show

- the Workforce Roster in Attendance
- the Logs page with completed attendance cycles

### What it proves

- the system is not only a live feed
- active state and historical state are separated intentionally
- completed cycles remain auditable

### What to say

The roster shows active attendance cycles, while Logs preserve historical
records. Once a worker completes both entry and exit, the live card clears from
the roster and the finished cycle remains in the log history.

## 4. Fleet Monitoring

### What I show

- the Fleet Monitoring page
- live MediaPipe-based face attachment and driver state

### What it proves

- the platform supports a second real-time computer-vision pipeline
- the system is broader than only gate recognition
- multiple monitoring workflows coexist in the same architecture

### What to say

This module uses a different runtime path from Attendance. Instead of identity
and PPE, it focuses on driver state such as face attachment, fatigue, and
distraction. It still follows the same local-first design: inference happens in
the backend runtime, and the browser displays the live state.

## 5. Authentication and Password Reset

### What I show

- the operator portal
- password reset request flow
- real email delivery behavior if needed

### What it proves

- this is a real operator platform, not an open dashboard
- the project includes a complete access-control layer
- the platform supports verified-domain email delivery

### What to say

The authentication layer includes registration approval, sign-in, password
change, and password reset. This matters because operators are making real
workflow decisions, so access control and auditability are part of the product,
not optional extras.

## 6. Chatbot

### What I show

- the Safety Chatbot page
- one concise prompt about the current system state

### What it proves

- the project is not only detection-focused
- operational data can be surfaced through a natural-language interface
- the platform includes an intelligence layer on top of the monitored state

### What to say

The chatbot sits on top of the platform state. Its job is not to perform the
vision pipeline itself, but to help an operator query the system in natural
language and get useful responses about attendance, PPE, alerts, and driver
events.

## 7. Architecture Conclusion

### What I show

- the architecture and system-flow documentation

### What it proves

- the project has a coherent engineering structure
- the modules are connected through a clear runtime design

### What to say

The most important technical point is that SafeGuard 360 is designed as a
local-first edge system with a browser control surface. The backend owns camera
access, local inference, state, and persistence; the frontend presents and
controls that runtime in real time.
