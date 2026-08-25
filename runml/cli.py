from __future__ import annotations
import argparse
import platform
import sys
import psutil

from . import __version__
from .config import get_data_dir, load_config, interactive_config, set_value
from .features import static_features
from .monitor import run_and_measure
from .storage import append_workload, read_workloads
from .validate import validate_command


def _cmd(parts):
    if parts and parts[0] == "--":
        parts = parts[1:]
    if not parts:
        raise RuntimeError("No command supplied.")
    return parts


def _mb(value):
    return f"{value / 1024:.2f} GB" if value >= 1024 else f"{value:.1f} MB"


def _show_config(cfg):
    print("RunML configuration")
    print("-------------------")
    print(f"Storage path             : {cfg['storage']['path']}")
    print(f"RAM metric               : {'ON' if cfg['metrics']['ram'] else 'OFF'}")
    print(f"CPU metric               : {'ON' if cfg['metrics']['cpu'] else 'OFF'}")
    print(f"App learning time        : {cfg['apps']['learn_seconds']} s")
    print(f"App sample interval      : {cfg['apps']['sample_interval']} s")
    print(f"Max apps                 : {cfg['apps']['max_apps']}")
    print(f"Min app RAM              : {cfg['apps']['min_ram_mb']} MB")
    print(f"Workload repetitions     : {cfg['workloads']['repetitions']}")
    print(f"Workload sample interval : {cfg['workloads']['sample_interval']} s")


def build_parser():
    p = argparse.ArgumentParser(prog="runml", description="Lightweight local ML resource predictor.")
    p.add_argument("--version", action="version", version=f"RunML {__version__}")
    sub = p.add_subparsers(dest="command")

    pc = sub.add_parser("config", help="View/change all RunML settings.")
    csub = pc.add_subparsers(dest="config_command")
    csub.add_parser("show")
    pcs = csub.add_parser("set")
    pcs.add_argument("key")
    pcs.add_argument("value")

    sub.add_parser("where")
    sub.add_parser("doctor")
    sub.add_parser("stats")

    pl = sub.add_parser("learn")
    pl.add_argument("target", nargs=argparse.REMAINDER)

    sub.add_parser("train")

    pp = sub.add_parser("predict")
    pp.add_argument("target", nargs=argparse.REMAINDER)

    pa = sub.add_parser("apps")
    asub = pa.add_subparsers(dest="apps_command")
    asub.add_parser("list")
    asub.add_parser("predict")
    asub.add_parser("learn")

    pone = sub.add_parser("app")
    onesub = pone.add_subparsers(dest="app_command")
    pol = onesub.add_parser("learn")
    pol.add_argument("name")
    pop = onesub.add_parser("predict")
    pop.add_argument("name")

    pr = sub.add_parser("remove")
    pr.add_argument("--yes", action="store_true")
    rsub = pr.add_subparsers(dest="remove_command")
    rsub.add_parser("all")
    rsub.add_parser("apps")
    rsub.add_parser("workloads")
    rsub.add_parser("models")
    rap = rsub.add_parser("app")
    rap.add_argument("name")
    rw = rsub.add_parser("workload")
    rw.add_argument("workload_id")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        data_dir = get_data_dir()
        cfg = load_config(data_dir)

        if args.command is None:
            parser.print_help()
            return 0

        if args.command == "config":
            if args.config_command is None:
                interactive_config()
            elif args.config_command == "show":
                _show_config(load_config())
            elif args.config_command == "set":
                path, new_cfg = set_value(args.key, args.value)
                print(f"Saved: {path}")
                _show_config(new_cfg)
            return 0

        # Storage may have changed.
        data_dir = get_data_dir()
        cfg = load_config(data_dir)

        if args.command == "where":
            print(data_dir)
            return 0

        if args.command == "doctor":
            from .apps import read_samples, trained_apps
            print("RunML doctor")
            print("------------")
            print(f"Version          : {__version__}")
            print(f"Python           : {platform.python_version()}")
            system = platform.system()
            machine = platform.machine()
            if system == "Windows":
                target = "Windows native"
            elif system == "Darwin" and machine.lower() == "arm64":
                target = "macOS Apple Silicon native"
            elif system == "Darwin":
                target = "UNSUPPORTED macOS architecture (Apple Silicon arm64 required)"
            else:
                target = "UNOFFICIAL platform"

            print(f"Platform         : {system} {platform.release()}")
            print(f"Architecture     : {machine}")
            print(f"Native target    : {target}")
            print(f"Data directory   : {data_dir}")
            print(f"RAM metric       : {'ON' if cfg['metrics']['ram'] else 'OFF'}")
            print(f"CPU metric       : {'ON' if cfg['metrics']['cpu'] else 'OFF'}")
            print(f"Workload samples : {len(read_workloads(data_dir))}")
            print(f"App samples      : {len(read_samples(data_dir))}")
            print(f"Trained apps     : {len(trained_apps(data_dir))}")
            print("Runtime deps     : psutil only")
            print("Background svc   : NONE")
            print("Telemetry        : NONE")
            print("Status           : OK")
            return 0

        if args.command == "stats":
            from .apps import read_samples, trained_apps
            print(f"Workload samples : {len(read_workloads(data_dir))}")
            print(f"App samples      : {len(read_samples(data_dir))}")
            print(f"Trained apps     : {', '.join(trained_apps(data_dir)) or 'none'}")
            return 0

        if args.command == "learn":
            command = _cmd(args.target)
            ok, error = validate_command(command)
            if not ok:
                print(f"RunML validation failed: {error}")
                print("Nothing was executed or recorded.")
                return 2

            repetitions = int(cfg["workloads"]["repetitions"])
            for i in range(repetitions):
                features = static_features(command)
                print(f"RunML learning run {i+1}/{repetitions}")
                print("-------------------")
                print(" ".join(command))
                measured = run_and_measure(command, cfg)

                if measured["exit_code"] != 0:
                    print(f"Run failed with exit code {measured['exit_code']}; not recorded.")
                    return measured["exit_code"] or 1

                path, archived = append_workload(data_dir, {**features, **measured})
                print(f"Runtime  : {measured['runtime_seconds']:.3f} s")
                if cfg["metrics"]["ram"]:
                    print(f"Peak RAM : {_mb(measured['peak_ram_mb'])}")
                if cfg["metrics"]["cpu"]:
                    print(f"Avg CPU  : {measured['avg_cpu_pct']:.2f}%")
                    print(f"Peak CPU : {measured['peak_cpu_pct']:.2f}%")
                print(f"Dataset  : {path}")
                if archived:
                    print(f"Legacy dataset archived: {archived}")
            return 0

        if args.command == "train":
            from .ml import train_models
            result = train_models(data_dir, read_workloads(data_dir), cfg)
            print("RunML training complete")
            print("-----------------------")
            print("Algorithm : pure-Python ridge regression")
            print(f"Workloads : {result['count']}")
            print(f"Model     : {result['path']}")
            return 0

        if args.command == "predict":
            from .ml import predict
            command = _cmd(args.target)
            ok, error = validate_command(command)
            if not ok:
                print(f"RunML validation failed: {error}")
                return 2
            features = static_features(command)
            result = predict(data_dir, features)

            print("RunML prediction")
            print("----------------")
            print(f"Workload          : {features['workload_id']}")
            print(f"Predicted runtime : {result['runtime_seconds']:.3f} s")
            if "peak_ram_mb" in result:
                available = psutil.virtual_memory().available / 1048576
                ratio = result["peak_ram_mb"] / max(available, 1)
                risk = "HIGH" if ratio >= 1 else ("MEDIUM" if ratio >= .75 else "LOW")
                print(f"Predicted peak RAM: {_mb(result['peak_ram_mb'])}")
                print(f"Memory risk       : {risk}")
            if "avg_cpu_pct" in result:
                print(f"Predicted avg CPU : {result['avg_cpu_pct']:.2f}%")
                print(f"Predicted peak CPU: {result['peak_cpu_pct']:.2f}%")
            print(f"Confidence        : {result['confidence']}")
            print(f"Training samples  : {result['samples']}")
            if result["extrapolation"]:
                print("Note              : extrapolation beyond training range")
            return 0

        if args.command == "apps":
            from .apps import list_apps, predict_app, trained_apps, collect_session

            if args.apps_command in {None, "list"}:
                print(f"{'APP':28} {'PROC':>5} {'RAM':>12}")
                print("-" * 48)
                for row in list_apps()[:50]:
                    print(f"{row['name'][:28]:28} {row['process_count']:>5} {_mb(row['ram_mb']):>12}")
                return 0

            if args.apps_command == "learn":
                candidates = [
                    row for row in list_apps()
                    if row["ram_mb"] >= float(cfg["apps"]["min_ram_mb"])
                ][:int(cfg["apps"]["max_apps"])]

                if not candidates:
                    print("No applications match the configured filters.")
                    return 0

                print(f"Learning {len(candidates)} applications using config settings...")
                for row in candidates:
                    name = row["name"]
                    try:
                        print(f"\n[{name}] observing for {cfg['apps']['learn_seconds']}s...")
                        result = collect_session(data_dir, name, cfg)
                        print(f"[{name}] +{result['samples_added']} samples; model updated.")
                    except Exception as exc:
                        print(f"[{name}] skipped: {exc}")
                print("\nRunML finished. No observer remains running.")
                return 0

            if args.apps_command == "predict":
                open_map = {row["name"].lower(): row["name"] for row in list_apps()}
                candidates = [name for name in trained_apps(data_dir) if name in open_map]
                if not candidates:
                    print("No trained applications are currently open.")
                    return 0

                headers = ["APP"]
                if cfg["metrics"]["ram"]:
                    headers += ["CURRENT RAM", "PRED RAM"]
                if cfg["metrics"]["cpu"]:
                    headers += ["CPU NOW", "PRED CPU"]
                headers += ["CONF"]
                print(" | ".join(headers))
                print("-" * 80)

                for name in candidates:
                    try:
                        r = predict_app(data_dir, name, cfg)
                        values = [name]
                        if "predicted_peak_ram_mb" in r:
                            values += [_mb(r["current_ram_mb"]), _mb(r["predicted_peak_ram_mb"])]
                        if "predicted_peak_cpu_pct" in r:
                            values += [f"{r['current_cpu_pct']:.1f}%", f"{r['predicted_peak_cpu_pct']:.1f}%"]
                        values += [r["confidence"]]
                        print(" | ".join(values))
                    except Exception as exc:
                        print(f"{name} | ERROR: {exc}")
                return 0

        if args.command == "app":
            from .apps import collect_session, predict_app

            if args.app_command == "learn":
                print(f"Observing {args.name} for {cfg['apps']['learn_seconds']}s using configured metrics...")
                result = collect_session(data_dir, args.name, cfg)
                print("App learning complete")
                print("---------------------")
                print(f"Samples added : {result['samples_added']}")
                print(f"Total samples : {result['total_samples']}")
                print(f"Model         : {result['model']}")
                if result["archived"]:
                    print(f"Legacy dataset archived: {result['archived']}")
                print("RunML has stopped observing.")
                return 0

            if args.app_command == "predict":
                r = predict_app(data_dir, args.name, cfg)
                print("RunML application prediction")
                print("----------------------------")
                print(f"Application      : {r['app_name']}")
                print(f"Processes        : {r['process_count']}")
                if "predicted_peak_ram_mb" in r:
                    print(f"Current RAM      : {_mb(r['current_ram_mb'])}")
                    print(f"Predicted RAM    : {_mb(r['predicted_peak_ram_mb'])}")
                if "predicted_peak_cpu_pct" in r:
                    print(f"Current CPU      : {r['current_cpu_pct']:.2f}%")
                    print(f"Predicted avg CPU: {r['predicted_avg_cpu_pct']:.2f}%")
                    print(f"Predicted peak CPU: {r['predicted_peak_cpu_pct']:.2f}%")
                print(f"Confidence       : {r['confidence']}")
                print(f"Training samples : {r['samples']}")
                return 0

        if args.command == "remove":
            from .remove import (
                interactive_remove, remove_all_learning, remove_apps, remove_models,
                remove_one_app, remove_one_workload, remove_workloads,
            )
            if args.remove_command is None:
                interactive_remove(data_dir)
                return 0

            funcs = {
                "all": lambda: remove_all_learning(data_dir, args.yes),
                "apps": lambda: remove_apps(data_dir, args.yes),
                "workloads": lambda: remove_workloads(data_dir, args.yes),
                "models": lambda: remove_models(data_dir, args.yes),
                "app": lambda: remove_one_app(data_dir, args.name, args.yes),
                "workload": lambda: remove_one_workload(data_dir, args.workload_id, args.yes),
            }
            print(funcs[args.remove_command]())
            return 0

        return 0

    except KeyboardInterrupt:
        print("\nRunML interrupted. No background observer remains.")
        return 130
    except Exception as exc:
        print(f"RunML error: {exc}", file=sys.stderr)
        return 1
