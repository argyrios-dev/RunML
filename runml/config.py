from __future__ import annotations

import json
import os
import platform
from copy import deepcopy
from pathlib import Path

APP_NAME = "RunML"
VERSION = "0.6.0"

DEFAULTS = {
    "schema_version": 6,
    "application": APP_NAME,
    "version": VERSION,
    "metrics": {
        "ram": True,
        "cpu": True,
    },
    "apps": {
        "learn_seconds": 20.0,
        "sample_interval": 0.5,
        "max_apps": 10,
        "min_ram_mb": 50.0,
    },
    "workloads": {
        "repetitions": 1,
        "sample_interval": 0.10,
    },
    "privacy": {
        "telemetry": False,
        "cloud": False,
        "background_service": False,
        "startup_service": False,
    },
}


def state_dir() -> Path:
    system = platform.system()

    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_NAME

    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    # Not an officially supported target, but keeping a sane fallback
    # makes development/testing possible.
    return Path.home() / ".config" / "runml"


def legacy_pointer_files() -> list[Path]:
    if platform.system() == "Darwin":
        return [Path.home() / ".config" / "runml" / "location.json"]
    return []


def pointer_file() -> Path:
    return state_dir() / "location.json"


def first_run_marker() -> Path:
    return state_dir() / "first-start.done"


def _deep_merge(base: dict, extra: dict) -> dict:
    out = deepcopy(base)
    for key, value in extra.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _write_pointer(data_dir: Path) -> None:
    path = pointer_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"data_dir": str(data_dir)}, indent=2),
        encoding="utf-8",
    )


def _parse_pointer(path: Path) -> Path | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["data_dir"]
        return Path(value).expanduser().resolve()
    except (OSError, KeyError, json.JSONDecodeError):
        return None


def _read_pointer() -> Path | None:
    current = _parse_pointer(pointer_file())
    if current is not None:
        return current

    # Migrate the pre-v0.6 macOS/Linux-style location pointer when present.
    for legacy in legacy_pointer_files():
        old = _parse_pointer(legacy)
        if old is not None:
            _write_pointer(old)
            return old

    return None


def config_path(data_dir: Path) -> Path:
    return data_dir / "config.json"


def ensure_data_dir(data_dir: Path) -> Path:
    data_dir = data_dir.expanduser().resolve()
    for folder in ("data", "models", "reports"):
        (data_dir / folder).mkdir(parents=True, exist_ok=True)
    return data_dir


def mark_first_run_complete() -> None:
    marker = first_run_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(VERSION, encoding="utf-8")


def first_run_setup() -> Path:
    previous = _read_pointer()

    print()
    print("RunML first start")
    print("-----------------")
    print("Choose where RunML should store datasets, models, reports and settings.")
    if previous is not None:
        print(f"Existing RunML location detected: {previous}")
        print("Type that path to keep it, or choose a new location.")
    print()

    while True:
        value = input("Data directory: ").strip()

        if not value:
            print("A data directory is required. RunML does not choose one automatically.")
            continue

        try:
            data_dir = ensure_data_dir(Path(value).expanduser())
            break
        except OSError as exc:
            print(f"Cannot use that directory: {exc}")

    _write_pointer(data_dir)
    save_config(DEFAULTS, data_dir)
    mark_first_run_complete()

    print()
    print(f"RunML data directory configured: {data_dir}")
    print("You can change it later with `runml config`.")
    print()
    return data_dir


def get_data_dir() -> Path:
    data_dir = _read_pointer()

    if not first_run_marker().exists():
        return first_run_setup()

    if data_dir is None:
        return first_run_setup()

    try:
        data_dir = ensure_data_dir(data_dir)
    except OSError:
        print("Configured RunML data directory is unavailable.")
        return first_run_setup()

    _write_pointer(data_dir)
    return data_dir


def load_config(data_dir: Path | None = None) -> dict:
    data_dir = ensure_data_dir(data_dir or get_data_dir())
    path = config_path(data_dir)

    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}

    merged = _deep_merge(DEFAULTS, existing)
    merged["schema_version"] = 6
    merged["application"] = APP_NAME
    merged["version"] = VERSION
    merged["storage"] = {"path": str(data_dir)}

    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged


def save_config(config: dict, data_dir: Path | None = None) -> Path:
    data_dir = ensure_data_dir(data_dir or get_data_dir())
    config = _deep_merge(DEFAULTS, config)
    config["schema_version"] = 6
    config["application"] = APP_NAME
    config["version"] = VERSION
    config["storage"] = {"path": str(data_dir)}

    path = config_path(data_dir)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def move_storage_path(new_path: str) -> Path:
    if not new_path.strip():
        raise ValueError("storage.path cannot be empty.")

    old_dir = get_data_dir()
    old_cfg = load_config(old_dir)

    new_dir = ensure_data_dir(Path(new_path).expanduser())
    _write_pointer(new_dir)

    new_cfg_path = config_path(new_dir)
    if new_cfg_path.exists():
        try:
            new_existing = json.loads(new_cfg_path.read_text(encoding="utf-8"))
            new_cfg = _deep_merge(old_cfg, new_existing)
        except (OSError, json.JSONDecodeError):
            new_cfg = old_cfg
    else:
        new_cfg = old_cfg

    save_config(new_cfg, new_dir)
    mark_first_run_complete()
    return new_dir


VALID_KEYS = {
    "metrics.ram": bool,
    "metrics.cpu": bool,
    "apps.learn_seconds": float,
    "apps.sample_interval": float,
    "apps.max_apps": int,
    "apps.min_ram_mb": float,
    "workloads.repetitions": int,
    "workloads.sample_interval": float,
    "storage.path": str,
}


def _parse_bool(value: str) -> bool:
    lower = value.strip().lower()
    if lower in {"1", "true", "yes", "y", "on", "si", "sí"}:
        return True
    if lower in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError("Use on/off, true/false, yes/no or 1/0.")


def set_value(key: str, value: str) -> tuple[Path, dict]:
    if key not in VALID_KEYS:
        raise ValueError(f"Unknown config key: {key}")

    if key == "storage.path":
        new_dir = move_storage_path(value)
        return config_path(new_dir), load_config(new_dir)

    cfg = load_config()
    kind = VALID_KEYS[key]

    if kind is bool:
        parsed = _parse_bool(value)
    elif kind is int:
        parsed = int(value)
    elif kind is float:
        parsed = float(value)
    else:
        parsed = value

    if key == "apps.learn_seconds" and parsed < 4:
        raise ValueError("apps.learn_seconds must be >= 4.")
    if key == "apps.sample_interval" and not 0.2 <= parsed <= 5:
        raise ValueError("apps.sample_interval must be between 0.2 and 5 seconds.")
    if key == "apps.max_apps" and not 1 <= parsed <= 50:
        raise ValueError("apps.max_apps must be between 1 and 50.")
    if key == "apps.min_ram_mb" and parsed < 0:
        raise ValueError("apps.min_ram_mb must be >= 0.")
    if key == "workloads.repetitions" and not 1 <= parsed <= 100:
        raise ValueError("workloads.repetitions must be between 1 and 100.")
    if key == "workloads.sample_interval" and not 0.02 <= parsed <= 5:
        raise ValueError("workloads.sample_interval must be between 0.02 and 5 seconds.")

    section, name = key.split(".", 1)
    cfg[section][name] = parsed
    path = save_config(cfg)
    return path, cfg


def interactive_config() -> None:
    while True:
        cfg = load_config()
        print()
        print("RunML configuration")
        print("-------------------")
        print(f"1. Storage path             : {cfg['storage']['path']}")
        print(f"2. RAM metric               : {'ON' if cfg['metrics']['ram'] else 'OFF'}")
        print(f"3. CPU metric               : {'ON' if cfg['metrics']['cpu'] else 'OFF'}")
        print(f"4. App learning time        : {cfg['apps']['learn_seconds']} s")
        print(f"5. App sample interval      : {cfg['apps']['sample_interval']} s")
        print(f"6. Max apps for apps learn  : {cfg['apps']['max_apps']}")
        print(f"7. Min app RAM              : {cfg['apps']['min_ram_mb']} MB")
        print(f"8. Workload repetitions     : {cfg['workloads']['repetitions']}")
        print(f"9. Workload sample interval : {cfg['workloads']['sample_interval']} s")
        print("0. Exit")
        choice = input("Select: ").strip()

        if choice == "0":
            return

        mapping = {
            "1": "storage.path",
            "2": "metrics.ram",
            "3": "metrics.cpu",
            "4": "apps.learn_seconds",
            "5": "apps.sample_interval",
            "6": "apps.max_apps",
            "7": "apps.min_ram_mb",
            "8": "workloads.repetitions",
            "9": "workloads.sample_interval",
        }

        key = mapping.get(choice)
        if not key:
            print("Invalid option.")
            continue

        value = input(f"New value for {key}: ").strip()
        try:
            set_value(key, value)
            print("Saved.")
        except Exception as exc:
            print(f"Error: {exc}")
