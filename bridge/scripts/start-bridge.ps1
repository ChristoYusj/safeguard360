$ErrorActionPreference = "Stop"

$bridgeRoot = Split-Path -Parent $PSScriptRoot
Set-Location $bridgeRoot

& npm.cmd run start
