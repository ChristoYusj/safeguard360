import os
from pathlib import Path

base = Path(__file__).resolve().parent

dirs = [
    # Backend
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
    # Frontend
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
    # Other
    'data/models',
    'data/faces',
    'data/snapshots',
    'data/videos',
    'scripts',
    'docs',
    'tests/test_data',
]

created = 0
for d in dirs:
    path = base / d
    os.makedirs(path, exist_ok=True)
    created += 1
    print(f'Created: {d}')

print(f'\nSuccessfully created {created} directories.')
