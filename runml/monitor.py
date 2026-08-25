from __future__ import annotations
import os
import subprocess
import time
import psutil


def _tree_processes(root):
    procs = [root]
    try:
        procs.extend(root.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return procs


def _tree_stats(root, want_ram=True, want_cpu=True):
    rss = 0
    cpu_time = 0.0
    for proc in _tree_processes(root):
        try:
            with proc.oneshot():
                if want_ram:
                    rss += proc.memory_info().rss
                if want_cpu:
                    ct = proc.cpu_times()
                    cpu_time += float(ct.user + ct.system)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return rss, cpu_time


def run_and_measure(command, config):
    want_ram = bool(config["metrics"]["ram"])
    want_cpu = bool(config["metrics"]["cpu"])
    interval = float(config["workloads"]["sample_interval"])
    cores = max(os.cpu_count() or 1, 1)

    started = time.perf_counter()
    process = subprocess.Popen(list(command), shell=False)
    root = psutil.Process(process.pid)

    peak_ram = 0.0
    peak_cpu = 0.0
    cpu_samples = []
    prev_cpu = None
    prev_t = None

    while True:
        code = process.poll()
        now = time.perf_counter()
        rss, cpu_time = _tree_stats(root, want_ram, want_cpu)

        if want_ram:
            peak_ram = max(peak_ram, rss / (1024 * 1024))

        if want_cpu and prev_cpu is not None and prev_t is not None:
            dt = max(now - prev_t, 1e-6)
            cpu_pct = max(0.0, (cpu_time - prev_cpu) / dt / cores * 100.0)
            peak_cpu = max(peak_cpu, cpu_pct)
            cpu_samples.append(cpu_pct)

        prev_cpu, prev_t = cpu_time, now

        if code is not None:
            break
        time.sleep(interval)

    runtime = time.perf_counter() - started

    return {
        "runtime_seconds": round(runtime, 6),
        "peak_ram_mb": round(peak_ram, 3) if want_ram else 0.0,
        "avg_cpu_pct": round(sum(cpu_samples) / len(cpu_samples), 4) if cpu_samples else 0.0,
        "peak_cpu_pct": round(peak_cpu, 4) if want_cpu else 0.0,
        "exit_code": int(code),
    }
