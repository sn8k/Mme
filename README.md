<!-- File Version: 0.4.0 -->
# Motion Frontend Rebuild

This repository hosts Motion Frontend, our fully owned control surface that supersedes the legacy UI described in [docs/cahier_des_charges.md](docs/cahier_des_charges.md) and [TODOs/TODO_frontend.md](TODOs/TODO_frontend.md). The target is a lightweight, headless-friendly UI served by the existing Tornado backend on Raspberry Pi systems.

## Quick Start - Raspberry Pi OS (Debian Trixie)

### One-liner Installation

```bash
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash
```

### Installation with Branch Selection

```bash
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --branch
```

### Uninstallation

```bash
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --uninstall
```

### Post-Installation

After installation, access the web interface at:
- **Local**: `http://localhost:8765`
- **Network**: `http://<raspberry-pi-ip>:8765`

Default credentials:
- **Username**: `admin`
- **Password**: `admin` (change on first login)

Service management:
```bash
sudo systemctl status motion-frontend   # Check status
sudo systemctl restart motion-frontend  # Restart
sudo journalctl -u motion-frontend -f   # View logs
```

---

## Objectives
- Deliver a cohesive replacement for the historic surveillance UI while keeping a modern yet dependency-free toolchain (vanilla HTML/CSS/JS rendered via Jinja2).
- Keep development fully cross-platform (Windows dev, Raspberry Pi deploy) while staying within the CPU/RAM budgets outlined in the cahier des charges.
- Enforce project-wide rules: strict i18n coverage, file-level semantic versioning (`X.Y.Z[letter]`), changelog-first releases, and documented install/update flows.

## Project Structure
```
templates/
  base.html
  main.html
  version.html
  manifest.json
static/
  css/{ui,main,frame}.css
  js/{ui,main,frame,version}.js
  js/motion_frontend.<lang>.json
  vendor/{jquery,gettext,...}
  img/motion-frontend-logo.svg
```
Additional tooling (e.g., vendor sync helpers, install scripts) will live under `tools/` and `scripts/` once requirements are finalized.

## Milestones
1. **Scaffolding** – establish templates, asset placeholders, and i18n loaders (current task).
2. **Functional parity** – port config rendering macros, AJAX flows, camera preview logic, and dependency handling.
3. **System integration** – wire RTSP/MJPEG endpoints, logging controls, update workflow, and hardware toggles.
4. **Install & CI** – deliver `install_motion_frontend.sh`, Raspberry Pi test plans, and release automation.

Progress will be tracked in the global changelog and via project issues. Every merge must update affected file versions and document the change.

## Windows installer
Use the PowerShell helper at [scripts/install_motion_frontend.ps1](scripts/install_motion_frontend.ps1) to roll out the templates and static assets on a Windows host. Successful installs and updates automatically launch the configured frontend URL (default `http://localhost:8765/`).

```
pwsh -File scripts/install_motion_frontend.ps1 -Mode install -TargetPath C:\MotionFrontend -Force -LaunchUrl "http://raspberrypi.local:8765/"
```

Use `-NoLaunch` to suppress the automatic browser launch, and `-ArchivePath` to emit a signed zip for Pi deployments. Modes `install`, `update`, and `uninstall` are supported.

## Windows launcher
For day-to-day development use [scripts/run_motion_frontend.ps1](scripts/run_motion_frontend.ps1). The script

- boots the Tornado backend (`backend/server.py`),
- waits for `/health` to respond, and
- opens your browser once the frontend is reachable.

```
pwsh -File scripts/run_motion_frontend.ps1 -PythonExe .venv/Scripts/python.exe -Host 127.0.0.1 -Port 9000 -LaunchUrl "http://localhost:9000/"
```

Pass `-NoBrowser` to keep the terminal-only workflow, or override paths (`-TemplatePath`, `-StaticPath`, `-ProjectRoot`) if you are running from a different checkout layout.

You can also invoke the backend directly for alternative environments:

```
python -m backend.server --host 0.0.0.0 --port 8765 --root . --template-path templates --static-path static
```
