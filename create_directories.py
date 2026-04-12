import os
from pathlib import Path

# Base path
base_path = Path(__file__).resolve().parent

# All directories to create
directories = [
    # Backend
    r'backend\app\config',
    r'backend\app\api',
    r'backend\app\websocket',
    r'backend\app\models',
    r'backend\app\db',
    r'backend\app\services',
    r'backend\app\camera',
    r'backend\app\inference',
    r'backend\app\pipeline',
    r'backend\app\decision',
    r'backend\app\actuator',
    r'backend\app\utils',
    r'backend\tests',
    
    # Frontend
    r'frontend\src\components\layout',
    r'frontend\src\components\common',
    r'frontend\src\components\live',
    r'frontend\src\components\attendance',
    r'frontend\src\components\events',
    r'frontend\src\components\alerts',
    r'frontend\src\components\enrollment',
    r'frontend\src\pages',
    r'frontend\src\hooks',
    r'frontend\src\services',
    r'frontend\src\context',
    r'frontend\src\utils',
    r'frontend\public',
    
    # Other
    r'data\models',
    r'data\faces',
    r'data\snapshots',
    r'data\videos',
    r'scripts',
    r'docs',
    r'tests\test_data',
]

# Create all directories
created_count = 0
for dir_path in directories:
    full_path = base_path / dir_path
    os.makedirs(full_path, exist_ok=True)
    created_count += 1
    print(f'Created: {dir_path}')

print(f'\nSuccess! All {created_count} directories created.')
