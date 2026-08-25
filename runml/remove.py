from __future__ import annotations
import csv
import shutil
from pathlib import Path
from .storage import WORKLOAD_FIELDS, rewrite_csv
from .apps import APP_FIELDS


def _confirm(text, yes):
    if yes:
        return True
    return input(f"{text} [y/N]: ").strip().lower() in {"y", "yes", "s", "si", "sí"}


def _remove_path(path):
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def remove_all_learning(data_dir, yes=False):
    if not _confirm("Delete ALL learning data, models and reports but KEEP settings?", yes):
        return "Cancelled."
    _remove_path(data_dir / "data")
    _remove_path(data_dir / "models")
    _remove_path(data_dir / "reports")
    for folder in ("data", "models", "reports"):
        (data_dir / folder).mkdir(parents=True, exist_ok=True)
    return "All learning data removed. Settings preserved."


def remove_models(data_dir, yes=False):
    if not _confirm("Delete all trained models?", yes):
        return "Cancelled."
    _remove_path(data_dir / "models")
    (data_dir / "models").mkdir(parents=True, exist_ok=True)
    return "All models removed."


def remove_workloads(data_dir, yes=False):
    if not _confirm("Delete all workload data and workload models?", yes):
        return "Cancelled."
    _remove_path(data_dir / "data" / "runs.csv")
    _remove_path(data_dir / "models" / "workloads.json")
    return "Workload data/models removed."


def remove_apps(data_dir, yes=False):
    if not _confirm("Delete all app data and app models?", yes):
        return "Cancelled."
    _remove_path(data_dir / "data" / "apps.csv")
    _remove_path(data_dir / "models" / "apps")
    return "App data/models removed."


def remove_one_app(data_dir, name, yes=False):
    target = Path(name).name.lower()
    if not _confirm(f"Delete data/model for {target}?", yes):
        return "Cancelled."

    path = data_dir / "data" / "apps.csv"
    if path.exists():
        with path.open("r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows = [r for r in rows if Path(r.get("app_name", "")).name.lower() != target]
        rewrite_csv(path, APP_FIELDS, rows)

    model_dir = data_dir / "models" / "apps"
    if model_dir.exists():
        for p in model_dir.glob("*.json"):
            try:
                import json
                if json.loads(p.read_text(encoding="utf-8")).get("app_name") == target:
                    p.unlink()
            except Exception:
                pass
    return f"Removed app data/model for {target}."


def remove_one_workload(data_dir, workload_id, yes=False):
    if not _confirm(f"Delete data for workload '{workload_id}'?", yes):
        return "Cancelled."

    path = data_dir / "data" / "runs.csv"
    if path.exists():
        with path.open("r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows = [r for r in rows if r.get("workload_id") != workload_id]
        rewrite_csv(path, WORKLOAD_FIELDS, rows)

    _remove_path(data_dir / "models" / "workloads.json")
    return f"Removed workload '{workload_id}'. Re-run `runml train` for remaining workloads."


def interactive_remove(data_dir):
    while True:
        print()
        print("RunML remove")
        print("------------")
        print("1. Remove one app")
        print("2. Remove all app data/models")
        print("3. Remove one workload")
        print("4. Remove all workload data/models")
        print("5. Remove all models only")
        print("6. Remove EVERYTHING except settings")
        print("0. Cancel")
        choice = input("Select: ").strip()

        if choice == "0":
            print("Cancelled.")
            return
        if choice == "1":
            print(remove_one_app(data_dir, input("App executable (e.g. msedge.exe): ").strip()))
            return
        if choice == "2":
            print(remove_apps(data_dir))
            return
        if choice == "3":
            print(remove_one_workload(data_dir, input("Workload ID: ").strip()))
            return
        if choice == "4":
            print(remove_workloads(data_dir))
            return
        if choice == "5":
            print(remove_models(data_dir))
            return
        if choice == "6":
            print(remove_all_learning(data_dir))
            return
        print("Invalid option.")
