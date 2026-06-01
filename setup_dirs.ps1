$dirs = @(
    "src\scriptmgr\core",
    "src\scriptmgr\api\routers",
    "src\scriptmgr\cli",
    "src\scriptmgr\executor",
    "src\scriptmgr\scheduler",
    "src\scriptmgr\workflows",
    "src\scriptmgr\notifications",
    "src\scriptmgr\service",
    "src\scriptmgr\web\templates",
    "src\scriptmgr\web\static",
    "alembic\versions",
    "tests\unit",
    "tests\integration",
    "samples",
    "docs",
    "data"
)
foreach ($d in $dirs) {
    $path = Join-Path $PSScriptRoot $d
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    Write-Host "Created $d"
}
Write-Host "`nAll directories created. Tell Copilot you're done." -ForegroundColor Green
