from __future__ import annotations
import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import psutil
from .regression import fit_ridge, predict_ridge
from .storage import _archive_if_legacy

APP_FIELDS = [
    "timestamp_utc", "app_name", "ram_mb", "ram_trend_mb_s", "cpu_pct",
    "cpu_trend_pct_s", "process_count", "thread_count", "handle_count",
    "read_rate_mb_s", "write_rate_mb_s", "available_ram_mb",
    "future_peak_ram_mb", "future_avg_cpu_pct", "future_peak_cpu_pct",
]

BASE_FEATURES = [
    "ram_mb", "ram_trend_mb_s", "cpu_pct", "cpu_trend_pct_s",
    "process_count", "thread_count", "handle_count", "read_rate_mb_s",
    "write_rate_mb_s", "available_ram_mb",
]


def _norm(name):
    return Path(name).name.lower()


def _matching(name):
    target = _norm(name)
    out = []
    for proc in psutil.process_iter(["name"]):
        try:
            if _norm(proc.info.get("name") or "") == target:
                out.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return out


def list_apps():
    grouped = {}
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            name = proc.info.get("name") or ""
            if not name:
                continue
            key = _norm(name)
            item = grouped.setdefault(key, {"name": name, "count": 0, "ram": 0})
            item["count"] += 1
            mem = proc.info.get("memory_info")
            if mem is not None:
                item["ram"] += int(mem.rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass

    rows = [{"name": v["name"], "process_count": v["count"], "ram_mb": v["ram"] / 1048576} for v in grouped.values()]
    rows.sort(key=lambda r: r["ram_mb"], reverse=True)
    return rows


def _raw(name, config):
    procs = _matching(name)
    if not procs:
        return None

    want_ram = config["metrics"]["ram"]
    want_cpu = config["metrics"]["cpu"]
    rss = threads = handles = read_bytes = write_bytes = 0
    cpu_time = 0.0
    accessible = 0

    for proc in procs:
        try:
            with proc.oneshot():
                if want_ram:
                    rss += proc.memory_info().rss
                threads += proc.num_threads()
                if want_cpu:
                    ct = proc.cpu_times()
                    cpu_time += float(ct.user + ct.system)
                try:
                    io = proc.io_counters()
                    read_bytes += int(io.read_bytes)
                    write_bytes += int(io.write_bytes)
                except (psutil.AccessDenied, AttributeError, NotImplementedError):
                    pass
                try:
                    handles += int(proc.num_handles())
                except (psutil.AccessDenied, AttributeError, NotImplementedError):
                    # macOS/Unix expose file descriptors rather than Windows handles.
                    try:
                        handles += int(proc.num_fds())
                    except (psutil.AccessDenied, AttributeError, NotImplementedError):
                        pass
            accessible += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass

    if accessible == 0:
        return None

    return {
        "t": time.monotonic(),
        "ram_mb": rss / 1048576 if want_ram else 0.0,
        "cpu_time": cpu_time,
        "process_count": float(accessible),
        "thread_count": float(threads),
        "handle_count": float(handles),
        "read_mb": read_bytes / 1048576,
        "write_mb": write_bytes / 1048576,
        "available_ram_mb": psutil.virtual_memory().available / 1048576,
    }


def _derive(prev, cur, config, prev_cpu_pct=0.0):
    result = {
        "ram_mb": cur["ram_mb"],
        "ram_trend_mb_s": 0.0,
        "cpu_pct": 0.0,
        "cpu_trend_pct_s": 0.0,
        "process_count": cur["process_count"],
        "thread_count": cur["thread_count"],
        "handle_count": cur["handle_count"],
        "read_rate_mb_s": 0.0,
        "write_rate_mb_s": 0.0,
        "available_ram_mb": cur["available_ram_mb"],
    }
    if prev is None:
        return result

    dt = max(cur["t"] - prev["t"], 1e-6)
    if config["metrics"]["ram"]:
        result["ram_trend_mb_s"] = (cur["ram_mb"] - prev["ram_mb"]) / dt
    if config["metrics"]["cpu"]:
        cores = max(os.cpu_count() or 1, 1)
        cpu = max(0.0, (cur["cpu_time"] - prev["cpu_time"]) / dt / cores * 100.0)
        result["cpu_pct"] = cpu
        result["cpu_trend_pct_s"] = (cpu - prev_cpu_pct) / dt

    result["read_rate_mb_s"] = max(0.0, (cur["read_mb"] - prev["read_mb"]) / dt)
    result["write_rate_mb_s"] = max(0.0, (cur["write_mb"] - prev["write_mb"]) / dt)
    return result


def current_features(name, config):
    interval = max(0.2, float(config["apps"]["sample_interval"]))
    a = _raw(name, config)
    if a is None:
        raise RuntimeError(f"Application/process not found: {name}")
    time.sleep(interval)
    b = _raw(name, config)
    if b is None:
        raise RuntimeError(f"Application closed while sampling: {name}")
    return _derive(a, b, config)


def _path(data_dir):
    return data_dir / "data" / "apps.csv"


def _append(data_dir, app_name, rows):
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    archived = _archive_if_legacy(path, APP_FIELDS)
    header = not path.exists() or path.stat().st_size == 0

    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=APP_FIELDS)
        if header:
            w.writeheader()
        for row in rows:
            payload = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "app_name": _norm(app_name), **row}
            w.writerow({k: payload.get(k, "") for k in APP_FIELDS})
    return path, archived


def read_samples(data_dir, app_name=None):
    path = _path(data_dir)
    if not path.exists() or path.stat().st_size == 0:
        return []

    target = _norm(app_name) if app_name else None
    rows = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != APP_FIELDS:
            return []
        for row in reader:
            try:
                name = _norm(row["app_name"])
                if target and name != target:
                    continue
                parsed = {"app_name": name}
                for field in APP_FIELDS:
                    if field not in {"timestamp_utc", "app_name"}:
                        parsed[field] = float(row[field])
                rows.append(parsed)
            except (KeyError, ValueError, TypeError):
                pass
    return rows


def _model_file(data_dir, app_name):
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in _norm(app_name))
    return data_dir / "models" / "apps" / f"{safe}.json"


def train_app_model(data_dir, app_name, config):
    rows = read_samples(data_dir, app_name)
    if len(rows) < 3:
        raise RuntimeError(f"Only {len(rows)} app samples are available.")

    models = {}
    if config["metrics"]["ram"]:
        models["ram"] = fit_ridge(rows, "future_peak_ram_mb", BASE_FEATURES, max_features=6, ridge=1e-3)
    if config["metrics"]["cpu"]:
        models["avg_cpu"] = fit_ridge(rows, "future_avg_cpu_pct", BASE_FEATURES, max_features=6, ridge=1e-3)
        models["peak_cpu"] = fit_ridge(rows, "future_peak_cpu_pct", BASE_FEATURES, max_features=6, ridge=1e-3)
    if not models:
        raise RuntimeError("Enable RAM and/or CPU in `runml config` before training apps.")

    payload = {"schema_version": 2, "app_name": _norm(app_name), "models": models}
    path = _model_file(data_dir, app_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    samples = next(iter(models.values()))["training_samples"]
    return {"path": path, "samples": samples}


def collect_session(data_dir, app_name, config):
    seconds = float(config["apps"]["learn_seconds"])
    interval = float(config["apps"]["sample_interval"])
    if seconds < 4:
        raise RuntimeError("apps.learn_seconds must be at least 4.")

    raw = []
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        snap = _raw(app_name, config)
        if snap is None:
            if not raw:
                raise RuntimeError(f"Application/process not found: {app_name}")
            break
        raw.append(snap)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))

    if len(raw) < 6:
        raise RuntimeError("Not enough snapshots. Increase apps.learn_seconds.")

    derived = []
    prev_cpu = 0.0
    for i, snap in enumerate(raw):
        d = _derive(raw[i-1] if i else None, snap, config, prev_cpu)
        prev_cpu = d["cpu_pct"]
        derived.append(d)

    horizon_steps = max(1, min(10, int(round(max(2.0, seconds * 0.25) / interval))))
    samples = []
    for i in range(1, len(derived) - horizon_steps):
        future_d = derived[i+1:i+1+horizon_steps]
        future_r = raw[i+1:i+1+horizon_steps]
        if not future_d:
            continue

        sample = dict(derived[i])
        sample["future_peak_ram_mb"] = max(x["ram_mb"] for x in future_r) if config["metrics"]["ram"] else 0.0
        cpu_values = [x["cpu_pct"] for x in future_d] if config["metrics"]["cpu"] else [0.0]
        sample["future_avg_cpu_pct"] = sum(cpu_values) / len(cpu_values)
        sample["future_peak_cpu_pct"] = max(cpu_values)
        samples.append(sample)

    if len(samples) < 3:
        raise RuntimeError("Session too short to create training samples.")

    path, archived = _append(data_dir, app_name, samples)
    model = train_app_model(data_dir, app_name, config)
    return {"path": path, "archived": archived, "samples_added": len(samples), "total_samples": model["samples"], "model": model["path"]}


def predict_app(data_dir, app_name, config):
    path = _model_file(data_dir, app_name)
    if not path.exists():
        raise RuntimeError(f"No model for '{app_name}'. Learn it first.")

    payload = json.loads(path.read_text(encoding="utf-8"))
    features = current_features(app_name, config)
    out = {
        "app_name": _norm(app_name),
        "current_ram_mb": features["ram_mb"],
        "current_cpu_pct": features["cpu_pct"],
        "process_count": int(features["process_count"]),
        "extrapolation": False,
    }

    models = payload["models"]
    samples = next(iter(models.values()))["training_samples"]
    out["samples"] = samples

    if "ram" in models:
        out["predicted_peak_ram_mb"], extra = predict_ridge(models["ram"], features)
        out["extrapolation"] |= extra
    if "avg_cpu" in models:
        out["predicted_avg_cpu_pct"], extra = predict_ridge(models["avg_cpu"], features)
        out["extrapolation"] |= extra
        out["predicted_peak_cpu_pct"], extra = predict_ridge(models["peak_cpu"], features)
        out["extrapolation"] |= extra

    out["confidence"] = "LOW" if out["extrapolation"] else ("HIGH" if samples >= 40 else "MEDIUM")
    return out


def trained_apps(data_dir):
    folder = data_dir / "models" / "apps"
    if not folder.exists():
        return []
    out = []
    for path in folder.glob("*.json"):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8"))["app_name"])
        except Exception:
            pass
    return sorted(set(out))
