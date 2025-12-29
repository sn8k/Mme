# File Version: 0.2.2
<#!
.SYNOPSIS
    Windows installer and lifecycle helper for Motion Frontend assets.

.DESCRIPTION
    Copies the Motion Frontend templates, static files, and documentation to a
    target directory on Windows. Supports install, update (with automatic
    backups), and uninstall operations so developers can configure a test
    deployment quickly.

.PARAMETER Mode
    Operation to execute: install, update, or uninstall.

.PARAMETER SourcePath
    Location of the Motion Frontend repository. Defaults to the repository root
    relative to this script.

.PARAMETER TargetPath
    Destination directory where the runtime assets will be installed. Defaults
    to %ProgramData%\MotionFrontend.

.PARAMETER Force
    Skips confirmation prompts and overwrites existing targets.

.PARAMETER LaunchUrl
    URL that should be opened in the default browser after a successful install
    or update. Defaults to http://localhost:8765/.

.PARAMETER NoLaunch
    Prevents automatic browser launch even after a successful install/update.

.PARAMETER LaunchProbeTimeoutSec
    Number of seconds to wait when probing the LaunchUrl before deciding to
    skip the automatic browser launch.

.PARAMETER ArchivePath
    Optional path to a .zip file. When provided, the script will create or
    refresh an archive of the installed assets after a successful install or
    update.

.EXAMPLE
    pwsh -File scripts/install_motion_frontend.ps1 -Mode install -TargetPath C:\MotionFrontend

.EXAMPLE
    pwsh -File scripts/install_motion_frontend.ps1 -Mode update -ArchivePath C:\Packages\motion-frontend.zip -Force

.EXAMPLE
    pwsh -File scripts/install_motion_frontend.ps1 -Mode uninstall -Force
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [ValidateSet('install', 'update', 'uninstall')]
    [string]$Mode = 'install',

    [string]$SourcePath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,

    [string]$TargetPath = (Join-Path $env:ProgramData 'MotionFrontend'),

    [switch]$Force,

    [string]$ArchivePath,

    [string]$LaunchUrl = 'http://localhost:8765/',

    [switch]$NoLaunch,

    [int]$LaunchProbeTimeoutSec = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-LatestChangelogVersion {
    param([string]$ChangelogPath)
    if (-not (Test-Path $ChangelogPath)) {
        return '0.0.0'
    }

    foreach ($line in Get-Content -Path $ChangelogPath) {
        if ($line -match '^##\s+([0-9]+\.[0-9]+\.[0-9]+)') {
            return $Matches[1]
        }
    }

    return '0.0.0'
}

function Get-GitCommitHash {
    param([string]$RepoPath)
    try {
        $gitExe = Get-Command git -ErrorAction Stop
        $commit = & $gitExe.Source -C $RepoPath rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and $commit) {
            return $commit.Trim()
        }
    }
    catch {
        Write-Verbose 'Git not available; skipping commit hash detection.'
    }

    return 'unknown'
}

function Copy-MotionFrontendContent {
    param(
        [string]$Source,
        [string]$Destination
    )

    $items = @('templates', 'static', 'docs', 'TODOs', 'README.md', 'CHANGELOG.md')
    foreach ($item in $items) {
        $sourceItem = Join-Path $Source $item
        if (-not (Test-Path $sourceItem)) {
            Write-Verbose "Skipping missing item '$item'"
            continue
        }

        $destItem = Join-Path $Destination $item
        if (Test-Path $destItem) {
            Remove-Item -Path $destItem -Recurse -Force
        }

        Copy-Item -Path $sourceItem -Destination $destItem -Recurse -Force
    }
}

function Write-InstallManifest {
    param(
        [string]$Destination,
        [string]$Version,
        [string]$Source,
        [string]$Commit
    )

    $manifest = [ordered]@{
        product     = 'Motion Frontend'
        version     = $Version
        installedAt = (Get-Date).ToString('o')
        sourcePath  = $Source
        targetPath  = $Destination
        gitCommit   = $Commit
        files       = @('templates', 'static', 'docs', 'TODOs')
    }

    $manifestPath = Join-Path $Destination 'install-manifest.json'
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestPath -Encoding UTF8
}

function New-ArchiveIfRequested {
    param(
        [string]$Source,
        [string]$Archive
    )

    if (-not $Archive) {
        return
    }

    $archiveDir = Split-Path -Path $Archive -Parent
    if ($archiveDir -and -not (Test-Path $archiveDir)) {
        New-Item -Path $archiveDir -ItemType Directory | Out-Null
    }

    if (Test-Path $Archive) {
        Remove-Item -Path $Archive -Force
    }

    Compress-Archive -Path (Join-Path $Source '*') -DestinationPath $Archive -Force
}

function Test-FrontendReachable {
    param(
        [string]$Url,
        [int]$TimeoutSec = 5
    )

    if ([string]::IsNullOrWhiteSpace($Url)) {
        return $false
    }

    try {
        $response = Invoke-WebRequest -Uri $Url -Method Head -UseBasicParsing -TimeoutSec $TimeoutSec
        if ($response.StatusCode -ge 500) {
            Write-Verbose "Probe returned HTTP $($response.StatusCode); skipping launch."
            return $false
        }
        return $true
    }
    catch {
        Write-Verbose "Probe failed for '$Url': $_"
        return $false
    }
}

function Invoke-LaunchFrontend {
    param(
        [string]$Url,
        [switch]$DisableLaunch,
        [int]$ProbeTimeoutSec = 5
    )

    if ($DisableLaunch) {
        Write-Verbose 'Launch suppressed by -NoLaunch.'
        return
    }

    if ([string]::IsNullOrWhiteSpace($Url)) {
        Write-Verbose 'Launch URL was empty; skipping browser open.'
        return
    }

    if (-not (Test-FrontendReachable -Url $Url -TimeoutSec $ProbeTimeoutSec)) {
        Write-Warning "Skipped browser launch because '$Url' is not reachable. Start the backend server first or adjust -LaunchUrl."
        return
    }

    try {
        Start-Process $Url | Out-Null
        Write-Host "Opening Motion Frontend at $Url"
    }
    catch {
        Write-Warning "Unable to launch '$Url': $_"
    }
}

function Invoke-Install {
    param([switch]$Overwrite)

    if (Test-Path $TargetPath) {
        if (-not $Overwrite) {
            throw "Target '$TargetPath' already exists. Use -Force or Mode update."
        }
        Remove-Item -Path $TargetPath -Recurse -Force
    }

    New-Item -Path $TargetPath -ItemType Directory | Out-Null
    Copy-MotionFrontendContent -Source $SourcePath -Destination $TargetPath

    $version = Get-LatestChangelogVersion -ChangelogPath (Join-Path $SourcePath 'CHANGELOG.md')
    $commit = Get-GitCommitHash -RepoPath $SourcePath
    Write-InstallManifest -Destination $TargetPath -Version $version -Source $SourcePath -Commit $commit

    New-ArchiveIfRequested -Source $TargetPath -Archive $ArchivePath
    Write-Host "Motion Frontend $version installed to $TargetPath"
}

function Invoke-Update {
    if (-not (Test-Path $TargetPath)) {
        throw "Target '$TargetPath' not found. Run install first."
    }

    $timestamp = Get-Date -Format 'yyyyMMddHHmmss'
    $backupPath = "$TargetPath-backup-$timestamp"
    Copy-Item -Path $TargetPath -Destination $backupPath -Recurse -Force
    Write-Host "Created backup at $backupPath"

    Copy-MotionFrontendContent -Source $SourcePath -Destination $TargetPath

    $version = Get-LatestChangelogVersion -ChangelogPath (Join-Path $SourcePath 'CHANGELOG.md')
    $commit = Get-GitCommitHash -RepoPath $SourcePath
    Write-InstallManifest -Destination $TargetPath -Version $version -Source $SourcePath -Commit $commit

    New-ArchiveIfRequested -Source $TargetPath -Archive $ArchivePath
    Write-Host "Motion Frontend updated to $version"
}

function Invoke-Uninstall {
    if (-not (Test-Path $TargetPath)) {
        Write-Warning "Nothing to remove at '$TargetPath'"
        return
    }

    if (-not $Force) {
        $confirmation = Read-Host "Delete '$TargetPath'? Type YES to continue"
        if ($confirmation -ne 'YES') {
            Write-Warning 'Uninstall canceled.'
            return
        }
    }

    Remove-Item -Path $TargetPath -Recurse -Force
    Write-Host "Removed Motion Frontend from $TargetPath"
}

if (-not (Test-Path $SourcePath)) {
    throw "Source path '$SourcePath' not found."
}

switch ($Mode) {
    'install' {
        if ($PSCmdlet.ShouldProcess($TargetPath, 'Install Motion Frontend')) {
            Invoke-Install -Overwrite:$Force
            Invoke-LaunchFrontend -Url $LaunchUrl -DisableLaunch:$NoLaunch -ProbeTimeoutSec $LaunchProbeTimeoutSec
        }
    }
    'update' {
        if ($PSCmdlet.ShouldProcess($TargetPath, 'Update Motion Frontend')) {
            Invoke-Update
            Invoke-LaunchFrontend -Url $LaunchUrl -DisableLaunch:$NoLaunch -ProbeTimeoutSec $LaunchProbeTimeoutSec
        }
    }
    'uninstall' {
        if ($PSCmdlet.ShouldProcess($TargetPath, 'Uninstall Motion Frontend')) {
            Invoke-Uninstall
        }
    }
}
