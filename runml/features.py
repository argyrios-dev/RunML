from __future__ import annotations
import os
from pathlib import Path
import psutil

MAX_FILES_TO_SCAN = 20_000


def _parse_number(value):
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _path_stats(path):
    if not path.exists():
        return 0, 0
    try:
        if path.is_file():
            return path.stat().st_size, 1
    except OSError:
        return 0, 0

    total = count = 0
    try:
        for item in path.rglob("*"):
            if count >= MAX_FILES_TO_SCAN:
                break
            try:
                if item.is_file():
                    total += item.stat().st_size
                    count += 1
            except OSError:
                pass
    except OSError:
        pass
    return total, count


def workload_id(command):
    exe = Path(command[0]).name.lower()
    if exe in {"python", "python.exe", "python3", "python3.exe", "py", "py.exe"}:
        for arg in command[1:]:
            if arg.lower().endswith(".py"):
                return f"{exe}:{Path(arg).name.lower()}"
    return exe


def static_features(command):
    nums = []
    total_bytes = total_files = 0

    for raw in command[1:]:
        num = _parse_number(raw)
        if num is not None:
            nums.append(num)
        candidate = Path(raw).expanduser()
        if candidate.exists():
            size, count = _path_stats(candidate)
            total_bytes += size
            total_files += count

    vm = psutil.virtual_memory()
    return {
        "workload_id": workload_id(command),
        "arg_count": float(max(0, len(command) - 1)),
        "primary_numeric_arg": float(nums[0] if nums else 0.0),
        "secondary_numeric_sum": float(sum(nums[1:]) if len(nums) > 1 else 0.0),
        "numeric_arg_count": float(len(nums)),
        "input_mb": float(total_bytes / (1024 * 1024)),
        "input_files": float(total_files),
        "cpu_count": float(os.cpu_count() or 1),
        "total_ram_mb": float(vm.total / (1024 * 1024)),
    }
