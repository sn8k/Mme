# File Version: 0.1.0
[CmdletBinding()]
param(
    [string]$PythonExe = "python",
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 8765,
    [string]$ProjectRoot,
    [string]$TemplatePath = "templates",
    [string]$StaticPath = "static",
    [string]$ChangelogPath = "CHANGELOG.md",
    [string]$Environment = "development",
    [string]$LogLevel = "INFO",
    [string]$LaunchUrl,
    [switch]$NoBrowser,
    [int]$ProbeTimeoutSeconds = 20,
    [int]$ProbeIntervalMilliseconds = 500
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-MfePath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$PathValue
    )

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        $candidate = $PathValue
    }
    else {
        $candidate = Join-Path -Path $BasePath -ChildPath $PathValue
    }

    if (-not (Test-Path -LiteralPath $candidate)) {
        throw "Path not found: $candidate"
    }

    return (Convert-Path -LiteralPath $candidate)
}

$script:InvokeSupportsBasicParsing = $null

function Test-MfeEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Uri
    )

    if ($null -eq $script:InvokeSupportsBasicParsing) {
        $script:InvokeSupportsBasicParsing = (Get-Command Invoke-WebRequest).Parameters.ContainsKey("UseBasicParsing")
    }

    $invokeParams = @{
        Method     = 'Get'
        Uri        = $Uri
        TimeoutSec = 3
    }

    if ($script:InvokeSupportsBasicParsing) {
        $invokeParams["UseBasicParsing"] = $true
    }

    try {
        $response = Invoke-WebRequest @invokeParams
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

function Stop-MfeBackend {
    param([System.Diagnostics.Process]$Process)

    if (-not $Process) {
        return
    }

    if (-not $Process.HasExited) {
        try {
            $null = $Process.CloseMainWindow()
            Start-Sleep -Milliseconds 500
        }
        catch {
            # no-op
        }
    }

    if (-not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

$backendProcess = $null

try {
    if (-not $ProjectRoot) {
        $ProjectRoot = Join-Path -Path $PSScriptRoot -ChildPath ".."
    }
    $ProjectRoot = (Convert-Path -LiteralPath $ProjectRoot)

    Write-Host "Using project root: $ProjectRoot"

    try {
        & $PythonExe --version | Out-Null
    }
    catch {
        throw "Python executable '$PythonExe' not found or not callable."
    }

    $resolvedTemplate = Resolve-MfePath -BasePath $ProjectRoot -PathValue $TemplatePath
    $resolvedStatic = Resolve-MfePath -BasePath $ProjectRoot -PathValue $StaticPath
    $resolvedChangelog = Resolve-MfePath -BasePath $ProjectRoot -PathValue $ChangelogPath

    $serverArgs = @(
        "-m", "backend.server",
        "--host", $BindAddress,
        "--port", $Port,
        "--root", $ProjectRoot,
        "--template-path", $resolvedTemplate,
        "--static-path", $resolvedStatic,
        "--changelog", $resolvedChangelog,
        "--environment", $Environment,
        "--log-level", $LogLevel
    )

    Write-Host "Launching backend: $PythonExe $($serverArgs -join ' ')"
    $backendProcess = Start-Process -FilePath $PythonExe -ArgumentList $serverArgs -WorkingDirectory $ProjectRoot -PassThru -NoNewWindow

    $probeHost = if ($BindAddress -eq "0.0.0.0" -or $BindAddress -eq "::") { "127.0.0.1" } else { $BindAddress }
    $healthUrl = "http://${probeHost}:${Port}/health"
    $deadline = (Get-Date).AddSeconds($ProbeTimeoutSeconds)
    $ready = $false

    while ((Get-Date) -lt $deadline) {
        if ($backendProcess.HasExited) {
            throw "Backend process exited early with code $($backendProcess.ExitCode)."
        }

        if (Test-MfeEndpoint -Uri $healthUrl) {
            $ready = $true
            break
        }

        Start-Sleep -Milliseconds $ProbeIntervalMilliseconds
    }

    if (-not $ready) {
        throw "Backend did not respond at $healthUrl within $ProbeTimeoutSeconds seconds."
    }

    Write-Host "Backend ready at $healthUrl"

    if (-not $NoBrowser) {
        if (-not $LaunchUrl) {
            $LaunchUrl = "http://localhost:${Port}/"
        }
        Write-Host "Opening $LaunchUrl"
        Start-Process $LaunchUrl | Out-Null
    }

    Write-Host "Press Ctrl+C to stop Motion Frontend." -ForegroundColor Green
    Wait-Process -Id $backendProcess.Id
    exit $backendProcess.ExitCode
}
finally {
    if ($backendProcess) {
        Stop-MfeBackend -Process $backendProcess
    }
}
