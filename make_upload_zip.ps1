# ============================================================================
# make_upload_zip.ps1 -- Build a clean upload zip for Claude/AI sessions.
#
# Strips bloat that .gitignore already knows about but Compress-Archive
# (and File Explorer's "Send to > Compressed folder") do NOT honor:
#
#   - venv/                     (~37 MB, never needed in chat)
#   - .git/                     (~24 MB, full git history)
#   - __pycache__/ everywhere   (~9 MB, regenerated on first import)
#   - .pytest_cache/            (test runner cache)
#   - *.pyc                     (compiled bytecode)
#   - *.log                     (test/runtime logs)
#   - *.db, *.db-wal, *.db-shm  (live SQLite database)
#
#   *** NEW (2026-05-30): static/maps/ painted substrates ***
#   The six *_substrate.png paintings are ~9.3 MB raw and ~9 MB even
#   zipped (PNG is already compressed), i.e. the bulk of the upload.
#   They are LIVE runtime assets (declared in area YAML, loaded by
#   engine/area_loader.py) -- so they stay on disk and in git -- but
#   the AI session does not need the binaries to work on code/design.
#   Excluding them takes the upload from ~15 MB to ~5 MB with zero
#   semantic loss. When a specific map's painting matters for a
#   session, attach that one PNG to the chat directly.
#
#   Need them in the zip anyway?  ->  .\make_upload_zip.ps1 -IncludeMaps
#
# Result: ~36 MB raw tree -> ~5 MB upload zip. Faster uploads, lower
# token cost, no semantic loss -- everything stripped is regenerable,
# lives in git, or can be attached on demand.
#
# Usage (from C:\SW_MUSH):
#   .\make_upload_zip.ps1                 # default: maps excluded
#   .\make_upload_zip.ps1 -IncludeMaps    # include the substrates
#
# Output:
#   %USERPROFILE%\Downloads\SW_MUSH_upload_<timestamp>.zip
#
# To verify what's in the zip without extracting:
#   Get-ChildItem ..\SW_MUSH_upload_*.zip | Select-Object Length,Name
# ============================================================================

param(
    [switch]$IncludeMaps   # opt back in to shipping static/maps/*.png
)

$ErrorActionPreference = 'Stop'

# Resolve project root (script can be run from anywhere)
$projectRoot = $PSScriptRoot
if (-not $projectRoot) { $projectRoot = (Get-Location).Path }

Push-Location $projectRoot
try {
    # Sanity: confirm we're in SW_MUSH
    if (-not (Test-Path '.\main.py') -or -not (Test-Path '.\engine')) {
        Write-Error "Doesn't look like SW_MUSH root (no main.py + engine/). Aborting."
        exit 1
    }

    $timestamp = Get-Date -Format 'yyyyMMdd_HHmm'
    $zipPath = Join-Path $env:USERPROFILE "Downloads\SW_MUSH_upload_$timestamp.zip"
    # Remove old zip with same timestamp if present (safety)
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

    Write-Host "=== Building clean upload zip ===" -ForegroundColor Cyan
    Write-Host "Source:      $projectRoot"
    Write-Host "Destination: $zipPath"
    if ($IncludeMaps) {
        Write-Host "Maps:        INCLUDED (-IncludeMaps)" -ForegroundColor Yellow
    } else {
        Write-Host "Maps:        excluded (static/maps/ substrates skipped)" -ForegroundColor Gray
    }
    Write-Host ""

    # Patterns to exclude (matched against full relative path with backslashes)
    $excludePatterns = @(
        '\\venv\\',
        '\\\.git\\',
        '\\__pycache__\\',
        '\\\.pytest_cache\\',
        '\\\.mypy_cache\\',
        '\\\.ruff_cache\\'
    )

    # The painted map substrates -- the bulk of the upload weight.
    # Skipped by default; -IncludeMaps puts them back.
    if (-not $IncludeMaps) {
        $excludePatterns += '\\static\\maps\\'
    }

    $excludeExtensions = @(
        '.pyc',
        '.pyo',
        '.log',
        '.db',
        '.db-wal',
        '.db-shm'
    )

    Write-Host "Scanning files..." -ForegroundColor Gray
    $allFiles = Get-ChildItem -Path $projectRoot -Recurse -File -Force

    $kept = New-Object System.Collections.Generic.List[System.IO.FileInfo]
    foreach ($f in $allFiles) {
        $rel = $f.FullName.Substring($projectRoot.Length)

        # Path-segment excludes
        $skip = $false
        foreach ($pat in $excludePatterns) {
            if ($rel -match $pat) { $skip = $true; break }
        }
        if ($skip) { continue }

        # Extension excludes
        if ($excludeExtensions -contains $f.Extension.ToLower()) { continue }

        $kept.Add($f) | Out-Null
    }

    $totalSize = ($kept | Measure-Object -Property Length -Sum).Sum
    $totalMB = [math]::Round($totalSize / 1MB, 2)

    Write-Host "Files included: $($kept.Count)" -ForegroundColor Green
    Write-Host "Uncompressed:   $totalMB MB" -ForegroundColor Green
    Write-Host ""
    Write-Host "Compressing..." -ForegroundColor Gray

    # Compress-Archive needs a relative-path layout to keep folder structure clean.
    # We stage paths relative to projectRoot.
    $relativePaths = $kept | ForEach-Object {
        $_.FullName.Substring($projectRoot.Length + 1)
    }

    # Compress-Archive can't take 8000+ paths cleanly on every Windows version,
    # so use .NET ZipFile directly for reliability.
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($f in $kept) {
            $rel = $f.FullName.Substring($projectRoot.Length + 1).Replace('\','/')
            $entry = $zip.CreateEntry($rel, [System.IO.Compression.CompressionLevel]::Optimal)
            $stream = $entry.Open()
            try {
                $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
                $stream.Write($bytes, 0, $bytes.Length)
            } finally {
                $stream.Dispose()
            }
        }
    } finally {
        $zip.Dispose()
    }

    $zipSize = (Get-Item $zipPath).Length
    $zipMB = [math]::Round($zipSize / 1MB, 2)

    Write-Host ""
    Write-Host "=== Done ===" -ForegroundColor Cyan
    Write-Host "Zip size:    $zipMB MB" -ForegroundColor Green
    Write-Host "Output:      $zipPath" -ForegroundColor Green
    Write-Host ""
    Write-Host "Upload this file to Claude. The previous zip is no longer needed." -ForegroundColor Yellow
}
finally {
    Pop-Location
}
