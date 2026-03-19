#!/usr/bin/env python3
"""
SafeGuard 360 - Directory Structure Generator
Creates all necessary directories for the project
"""

import os

# Define all directories to be created
directories = [
    'backend/app/config',
    'backend/app/api',
    'backend/app/websocket',
    'backend/app/models',
    'backend/app/db',
    'backend/app/services',
    'backend/app/camera',
    'backend/app/inference',
    'backend/app/pipeline',
    'backend/app/decision',
    'backend/app/actuator',
    'backend/app/utils',
    'backend/tests',
    'frontend/src/components/layout',
    'frontend/src/components/common',
    'frontend/src/components/live',
    'frontend/src/components/attendance',
    'frontend/src/components/events',
    'frontend/src/components/alerts',
    'frontend/src/components/enrollment',
    'frontend/src/pages',
    'frontend/src/hooks',
    'frontend/src/services',
    'frontend/src/context',
    'frontend/src/utils',
    'frontend/public',
    'data/models',
    'data/faces',
    'data/snapshots',
    'data/videos',
    'scripts',
    'docs',
    'tests/test_data'
]

# Create all directories
print("Creating SafeGuard 360 project directories...\n")
for directory in directories:
    os.makedirs(directory, exist_ok=True)
    print(f"✓ Created: {directory}")

print(f"\n✓ Total directories created: {len(directories)}")
print("Project structure setup complete!")
