from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path

WORKLOAD_FIELDS = [
    "timestamp_utc", "workload_id", "arg_count", "primary_numeric_arg",
    "secondary_numeric_sum", "numeric_arg_count", "input_mb", "input_files",
    "cpu_count", "total_ram_mb", "runtime_seconds", "peak_ram_mb",
    "avg_cpu_pct", "peak_cpu_pct", "exit_code",
]


def _archive_if_legacy(path: Path, expected_fields: list[str]) -> Path | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        with path.open("r", newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
    except OSError:
        return None

    if header == expected_fields:
        return None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archived = path.with_name(f"{path.stem}.legacy-{stamp}{path.suffix}")
    path.rename(archived)
    return archived


def append_workload(data_dir: Path, row: dict):
    path = data_dir / "data" / "runs.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    archived = _archive_if_legacy(path, WORKLOAD_FIELDS)
    header = not path.exists() or path.stat().st_size == 0
    payload = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), **row}

    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=WORKLOAD_FIELDS)
        if header:
            w.writeheader()
        w.writerow({k: payload.get(k, "") for k in WORKLOAD_FIELDS})
    return path, archived


def read_workloads(data_dir: Path):
    path = data_dir / "data" / "runs.csv"
    if not path.exists() or path.stat().st_size == 0:
        return []

    rows = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != WORKLOAD_FIELDS:
            return []
        for row in reader:
            try:
                if int(float(row["exit_code"])) != 0:
                    continue
                parsed = {"workload_id": row["workload_id"]}
                for field in WORKLOAD_FIELDS:
                    if field not in {"timestamp_utc", "workload_id"}:
                        parsed[field] = float(row[field])
                rows.append(parsed)
            except (KeyError, ValueError, TypeError):
                continue
    return rows


def rewrite_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    if not rows:
        if path.exists():
            path.unlink()
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})
