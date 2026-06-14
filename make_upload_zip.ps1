# ============================================================================
# make_upload_zip.ps1 -- Build a clean upload zip for Claude/AI sessions.
#
# WHAT IT SHIPS (2026-06-12 rewrite): exactly the files git considers part of
# the project -- tracked files PLUS new untracked work -- and nothing git
# ignores. The file list comes from git, not a whole-tree walk + blacklist:
#
#     git ls-files                          (everything tracked)
#   + git ls-files --others --exclude-standard   (new files not yet committed,
#                                                  e.g. a drop you haven't
#                                                  committed yet)
#
# Because .gitignore is the authority, ALL of the bloat is excluded for free,
# now and for any FUTURE bloat, with no list to maintain:
#
#   - venv/ (~87 MB)            - node_modules/ (~25 MB, VSCode ext deps)
#   - .git/ (~24 MB)            - docs/sourcebooks/ (~23 MB WEG PDFs, copyright)
#   - __pycache__/, *.pyc       - .pytest_cache/, .mypy_cache/, .ruff_cache/
#   - *.db / *.db-wal / *.db-shm (live SQLite)   - *.log
#
# The OLD script walked the entire 36 MB+ tree and hand-excluded a fixed list;
# when node_modules/ and the sourcebook PDF appeared (untracked, so NOT on the
# list) the zip ballooned 5 MB -> 30 MB+. Driving the list from git fixes that
# class of regression permanently: anything .gitignore knows about can never
# leak in again.
#
# MAP SUBSTRATES: static/maps/*_substrate.png are tracked (live runtime assets)
# but are ~9 MB of already-compressed PNG that an AI session doesn't need to
# work on code/design. Excluded by default; -IncludeMaps ships them. When one
# specific map's painting matters, attach that PNG to the chat directly.
#
# Result: ~5 MB upload zip, no semantic loss -- everything omitted is in git,
# regenerable, or attachable on demand.
#
# Usage (from C:\SW_MUSH):
#   .\make_upload_zip.ps1                 # default: full tracked source, maps excluded (~8 MB)
#   .\make_upload_zip.ps1 -Lean           # also drop tests/ -- progress/design review (~6 MB)
#   .\make_upload_zip.ps1 -IncludeMaps    # add the static/maps substrates back (~17 MB)
#   .\make_upload_zip.ps1 -Lean -IncludeMaps   # flags compose
#
# Output:
#   %USERPROFILE%\Downloads\SW_MUSH_upload_<timestamp>.zip
#
# To verify what's in the zip without extracting:
#   Get-ChildItem $env:USERPROFILE\Downloads\SW_MUSH_upload_*.zip | Select-Object Length,Name
# ============================================================================

param(
    [switch]$IncludeMaps,  # opt back in to shipping static/maps/*.png
    [switch]$Lean          # drop tests/ (the suite source) for a smaller progress-review zip
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
    # Sanity: we drive the file list from git, so we must be in a git work tree.
    & git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Not inside a git work tree -- this script builds the file list from 'git ls-files'. Aborting."
        exit 1
    }

    $timestamp = Get-Date -Format 'yyyyMMdd_HHmm'
    $zipPath = Join-Path $env:USERPROFILE "Downloads\SW_MUSH_upload_$timestamp.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

    Write-Host "=== Building clean upload zip (git-driven file list) ===" -ForegroundColor Cyan
    Write-Host "Source:      $projectRoot"
    Write-Host "Destination: $zipPath"
    if ($IncludeMaps) {
        Write-Host "Maps:        INCLUDED (-IncludeMaps)" -ForegroundColor Yellow
    } else {
        Write-Host "Maps:        excluded (static/maps/ substrates skipped)" -ForegroundColor Gray
    }
    if ($Lean) {
        Write-Host "Tests:       excluded (-Lean -- progress/design review zip)" -ForegroundColor Yellow
    } else {
        Write-Host "Tests:       included (pass -Lean to drop the suite source)" -ForegroundColor Gray
    }
    Write-Host ""

    # ---- File list = tracked + new-untracked, straight from git --------------
    # git ls-files                       -> all tracked files
    # git ls-files --others --exclude-standard -> untracked files NOT ignored by
    #   .gitignore (so a drop you've written but not committed still ships, while
    #   venv/node_modules/sourcebooks/caches stay out automatically).
    Write-Host "Resolving file list from git..." -ForegroundColor Gray
    $tracked   = & git ls-files
    $untracked = & git ls-files --others --exclude-standard
    $relList   = @($tracked) + @($untracked) | Where-Object { $_ -and ($_.Trim().Length -gt 0) } | Sort-Object -Unique

    # Map-substrate exclusion (the one thing we drop that git DOES track).
    if (-not $IncludeMaps) {
        $relList = $relList | Where-Object { $_ -notmatch '^static/maps/' }
    }

    # Lean mode: drop the test suite source (tests/ is ~7 MB, ~28% of the zip).
    # The AI session needs it to debug a specific failing test, but NOT to weigh
    # in on progress/design -- the common case. Default ships tests; -Lean omits.
    if ($Lean) {
        $relList = $relList | Where-Object { $_ -notmatch '^tests/' }
    }

    # git returns forward-slash relative paths; resolve to files on disk and
    # skip any that vanished between the git call and now (rare, but safe).
    $kept = New-Object System.Collections.Generic.List[object]
    $missing = 0
    foreach ($rel in $relList) {
        $full = Join-Path $projectRoot ($rel -replace '/', '\')
        if (Test-Path -LiteralPath $full -PathType Leaf) {
            $kept.Add([pscustomobject]@{ Rel = $rel; Full = (Resolve-Path -LiteralPath $full).Path }) | Out-Null
        } else {
            $missing++
        }
    }

    $totalSize = ($kept | ForEach-Object { (Get-Item -LiteralPath $_.Full).Length } | Measure-Object -Sum).Sum
    $totalMB = [math]::Round($totalSize / 1MB, 2)

    Write-Host "Files included: $($kept.Count)" -ForegroundColor Green
    if ($missing -gt 0) { Write-Host "Skipped (listed by git but not on disk): $missing" -ForegroundColor DarkGray }
    Write-Host "Uncompressed:   $totalMB MB" -ForegroundColor Green
    Write-Host ""
    Write-Host "Compressing..." -ForegroundColor Gray

    # Use .NET ZipFile directly (Compress-Archive chokes on thousands of paths).
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($f in $kept) {
            $entry  = $zip.CreateEntry($f.Rel, [System.IO.Compression.CompressionLevel]::Optimal)
            $stream = $entry.Open()
            try {
                $bytes = [System.IO.File]::ReadAllBytes($f.Full)
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
    if ($zipMB -gt 25) {
        Write-Host "WARNING: zip is unexpectedly large (>25 MB). Something tracked-or-new is heavy --" -ForegroundColor Red
        Write-Host "         run:  git ls-files | % { [pscustomobject]@{ MB=[math]::Round((Get-Item `$_ -EA SilentlyContinue).Length/1MB,2); F=`$_ } } | sort MB -desc | select -First 15" -ForegroundColor Red
    } else {
        Write-Host "Upload this file to Claude. The previous zip is no longer needed." -ForegroundColor Yellow
    }
}
finally {
    Pop-Location
}
