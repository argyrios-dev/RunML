from __future__ import annotations
import shutil
from pathlib import Path

PYTHON_NAMES = {"python", "python.exe", "python3", "python3.exe", "py", "py.exe"}


def validate_command(command):
    if not command:
        return False, "No command supplied."

    exe = command[0]
    if not Path(exe).exists() and shutil.which(exe) is None:
        return False, f"Executable not found: {exe}"

    if Path(exe).name.lower() in PYTHON_NAMES:
        for arg in command[1:]:
            if arg.lower().endswith(".py"):
                if not Path(arg).expanduser().exists():
                    return False, f"Python script not found: {arg}"
                break
    return True, None
