# Directory Structure Creation - Instructions

## Overview

All necessary scripts and batch files have been created to build the complete directory structure for the Safeguard360 project.

## Files Created

1. **CREATE_DIRS.bat** - Batch file for Command Prompt
2. **create-dirs.ps1** - PowerShell script
3. **setup_safeguard360.py** - Python script
4. **create_all_dirs.py** - Python script (alternative)

## How to Run

### Option 1: Batch File (Recommended for Windows)

```bash
# In Command Prompt:
cd <repo-root>
CREATE_DIRS.bat
```

Or simply double-click `CREATE_DIRS.bat` in File Explorer.

### Option 2: PowerShell Script

```powershell
# In PowerShell:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
cd <repo-root>
.\create-dirs.ps1
```

### Option 3: Python Script

```bash
# In Command Prompt:
cd <repo-root>
python create_all_dirs.py
# or
python setup_safeguard360.py
```

## Directory Structure to be Created

### Backend (13 directories)

```
backend/
  app/
    config/
    api/
    websocket/
    models/
    db/
    services/
    camera/
    inference/
    pipeline/
    decision/
    actuator/
    utils/
  tests/
```

### Frontend (13 directories)

```
frontend/
  src/
    components/
      layout/
      common/
      live/
      attendance/
      events/
      alerts/
      enrollment/
    pages/
    hooks/
    services/
    context/
    utils/
  public/
```

### Other (7 directories)

```
data/
  models/
  faces/
  snapshots/
  videos/
scripts/
docs/
tests/
  test_data/
```

## Total: 33 directories

## Troubleshooting

**If the batch file doesn't work:**

- Try the PowerShell script instead
- Or use the Python script
- Make sure you have permissions to create folders in the target directory

**If PowerShell execution policy error:**
Run this in PowerShell as Administrator:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**If Python script fails:**

- Ensure Python is installed and in your PATH
- Run: `python -m setup_safeguard360`

## Verification

After running any script, you should see all 33 directories created under:
`<repo-root>`

You can verify by opening File Explorer and browsing to the location, or run:

```cmd
dir /s /b <repo-root>
```
