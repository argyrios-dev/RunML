from __future__ import annotations
import json
from collections import defaultdict
from .regression import fit_ridge, predict_ridge

FEATURES = [
    "primary_numeric_arg", "secondary_numeric_sum", "input_mb", "input_files",
    "arg_count", "numeric_arg_count", "cpu_count", "total_ram_mb",
]


def train_models(data_dir, rows, config):
    if len(rows) < 5:
        raise RuntimeError(f"Only {len(rows)} compatible samples are available. Need at least 5.")

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["workload_id"]].append(row)

    workloads = {}
    for wid, group in grouped.items():
        if len(group) < 5:
            continue
        models = {
            "runtime": fit_ridge(group, "runtime_seconds", FEATURES, max_features=4),
        }
        if config["metrics"]["ram"]:
            models["ram"] = fit_ridge(group, "peak_ram_mb", FEATURES, max_features=4)
        if config["metrics"]["cpu"]:
            models["avg_cpu"] = fit_ridge(group, "avg_cpu_pct", FEATURES, max_features=4)
            models["peak_cpu"] = fit_ridge(group, "peak_cpu_pct", FEATURES, max_features=4)
        workloads[wid] = models

    if not workloads:
        raise RuntimeError("No workload has at least 5 compatible samples.")

    payload = {
        "schema_version": 4,
        "algorithm": "pure_python_standardized_ridge",
        "metrics": config["metrics"],
        "workloads": workloads,
    }
    path = data_dir / "models" / "workloads.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"path": path, "count": len(workloads)}


def predict(data_dir, features):
    path = data_dir / "models" / "workloads.json"
    if not path.exists():
        raise RuntimeError("Workload model not found. Run `runml train` first.")

    payload = json.loads(path.read_text(encoding="utf-8"))
    wid = features["workload_id"]
    if wid not in payload["workloads"]:
        raise RuntimeError(f"No trained model for workload '{wid}'.")

    models = payload["workloads"][wid]
    out = {"samples": models["runtime"]["training_samples"], "extrapolation": False}

    runtime, extra = predict_ridge(models["runtime"], features)
    out["runtime_seconds"] = runtime
    out["extrapolation"] |= extra

    if "ram" in models:
        out["peak_ram_mb"], extra = predict_ridge(models["ram"], features)
        out["extrapolation"] |= extra

    if "avg_cpu" in models:
        out["avg_cpu_pct"], extra = predict_ridge(models["avg_cpu"], features)
        out["extrapolation"] |= extra
        out["peak_cpu_pct"], extra = predict_ridge(models["peak_cpu"], features)
        out["extrapolation"] |= extra

    out["confidence"] = "LOW" if out["extrapolation"] else ("HIGH" if out["samples"] >= 20 else "MEDIUM")
    return out
