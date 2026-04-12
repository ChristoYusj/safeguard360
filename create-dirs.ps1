$basePath = $PSScriptRoot

$directories = @(
    # Backend
    "backend\app\config",
    "backend\app\api",
    "backend\app\websocket",
    "backend\app\models",
    "backend\app\db",
    "backend\app\services",
    "backend\app\camera",
    "backend\app\inference",
    "backend\app\pipeline",
    "backend\app\decision",
    "backend\app\actuator",
    "backend\app\utils",
    "backend\tests",
    
    # Frontend
    "frontend\src\components\layout",
    "frontend\src\components\common",
    "frontend\src\components\live",
    "frontend\src\components\attendance",
    "frontend\src\components\events",
    "frontend\src\components\alerts",
    "frontend\src\components\enrollment",
    "frontend\src\pages",
    "frontend\src\hooks",
    "frontend\src\services",
    "frontend\src\context",
    "frontend\src\utils",
    "frontend\public",
    
    # Other
    "data\models",
    "data\faces",
    "data\snapshots",
    "data\videos",
    "scripts",
    "docs",
    "tests\test_data"
)

Write-Host "Creating directory structure in: $basePath`n"

$count = 0
foreach ($dir in $directories) {
    $fullPath = Join-Path $basePath $dir
    New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    $count++
    Write-Host "✓ Created: $dir"
}

Write-Host "`nSuccessfully created $count directories!"
