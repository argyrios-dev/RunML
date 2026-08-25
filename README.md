# RunML v0.6.0

RunML is a lightweight local classical-machine-learning CLI for predicting
resource usage of workloads and running applications.

## Official platforms

- **Windows 10/11** — requires **Python 3.10 or newer**
- **macOS on Apple Silicon (arm64: M1 or newer)** — requires **Python 3.10 or newer**

The application logic is shared Python code. Platform-specific installers create
a private native Python runtime and expose the same global command:

```text
runml
```

RunML has no daemon, startup service, cloud component or telemetry.

Direct runtime dependency:

```text
psutil
```

The regression implementation remains pure Python and trained models are JSON.

---

## Windows install / update

Open PowerShell in the extracted RunML folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

Installed runtime:

```text
%LOCALAPPDATA%\RunML\runtime
```

Terminal command:

```text
%LOCALAPPDATA%\RunML\bin\runml.cmd
```

The installer replaces an older RunML runtime automatically.

If an existing RunML data location contains datasets/models/reports, the installer
asks:

```text
Delete previous TRAINED DATA/models/reports before upgrading? [y/N]
```

- `N` / Enter: preserve existing trained data and settings.
- `Y`: remove learning data/models/reports but preserve `config.json` and the
  selected storage location.

---

## macOS Apple Silicon install / update

Requirements:

- Apple Silicon Mac (M1 or newer)
- native **arm64** Python 3.10+

Run:

```bash
chmod +x install.sh
./install.sh
```

The installer verifies that the Mac is Apple Silicon and that Python itself is
running natively as `arm64`. It refuses to install with x86_64/Rosetta Python.

Installed runtime:

```text
~/Library/Application Support/RunML/runtime
```

Terminal launcher:

```text
~/.local/bin/runml
```

The installer adds `~/.local/bin` to `~/.zprofile` using a clearly marked RunML
block. No `sudo` is required.

Like Windows, `install.sh` replaces the previous RunML runtime and asks whether
existing trained data should be preserved or removed.

---

## First start

A fresh installation does **not** choose a default data path.

Run:

```text
runml
```

RunML requires the user to type a storage location:

```text
RunML first start
-----------------
Choose where RunML should store datasets, models, reports and settings.

Data directory:
```

An empty path is rejected.

On an update, if RunML already has a valid data location, that location/settings
are preserved and the first-start question is not repeated.

---

## Same commands on both platforms

```text
runml
runml --version
runml doctor
runml where

runml config
runml config show
runml config set metrics.ram on
runml config set metrics.cpu on

runml learn -- <command>
runml train
runml predict -- <command>

runml apps
runml apps learn
runml apps predict
runml app learn <process-name>
runml app predict <process-name>

runml remove
runml remove all
runml remove apps
runml remove workloads
runml remove models
```

Examples:

Windows:

```powershell
runml app learn msedge.exe
runml app predict msedge.exe
```

macOS:

```bash
runml app learn Safari
runml app predict Safari
```

Use `runml apps` to see the process names RunML sees on the current machine.

---

## CPU + RAM

RAM and CPU analysis are enabled by default.

Workloads can learn/predict:

- runtime
- peak RAM
- average CPU
- peak CPU

Applications can learn/predict:

- near-future RAM peak
- near-future average CPU
- near-future peak CPU

App process aggregation is cross-platform. On Windows RunML can use handle counts;
on macOS it falls back to file-descriptor counts when Windows-style handles are
not available.

---

## Architecture

```text
Windows PowerShell / CMD / Terminal
             |
           runml
             |
%LOCALAPPDATA%\RunML private runtime

macOS Terminal
             |
           runml
             |
~/Library/Application Support/RunML private arm64 runtime
             |
       shared Python core
```

No process remains running after a RunML command ends.

---

## Uninstall

Windows:

```powershell
& "$env:LOCALAPPDATA\RunML\uninstall.ps1"
```

macOS:

```bash
"$HOME/Library/Application Support/RunML/uninstall.sh"
```

Uninstalling the terminal/runtime integration does not delete the user's selected
data directory.
