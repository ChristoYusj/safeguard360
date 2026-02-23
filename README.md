# SafeGuard 360

AI-powered site and fleet safety monitoring platform.

## MVP Scope

### Site

- PPE Detection
- Attendance Logging
- Fall / Man-Down Detection

### Fleet

- Fatigue & Eye Distraction Detection
- Route Compliance Monitoring

### Command Platform

- Manager & Worker Roles
- Event Dashboard
- Incident Logging

## Architecture

Edge Devices → Event API → Backend → Dashboard

## Project Structure

- backend/ API, database, auth
- edge-site/ On-site camera inference
- edge-fleet/ In-vehicle AI detection
- web-dashboard/ Manager interface
- docs/ Architecture and design docs
