"""Thin adb wrapper. Arguments go to adb as a list (no PC shell), and every
part that reaches the phone's shell is quoted with shlex.quote."""

from __future__ import annotations

import os
import shlex
import subprocess

ADB = os.environ.get("POCKETPILOT_ADB", "adb")
SERIAL = os.environ.get("ANDROID_SERIAL")  # adb reads this too; kept for clarity


class AdbError(RuntimeError):
    pass


def adb(*args: str, timeout: int = 30, binary: bool = False):
    cmd = [ADB, *(["-s", SERIAL] if SERIAL else []), *args]
    try:
        # stdin=DEVNULL: otherwise adb reads the terminal's input and eats answers
        # meant for PocketPilot's prompts.
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, text=not binary,
                           stdin=subprocess.DEVNULL,
                           **({} if binary else {"encoding": "utf-8", "errors": "replace"}))
    except FileNotFoundError as e:
        raise AdbError("adb not found. Install Android platform-tools.") from e
    if r.returncode != 0:
        err = r.stderr if not binary else r.stderr.decode(errors="replace")
        raise AdbError(err.strip() or f"adb exited {r.returncode}")
    return r.stdout if binary else r.stdout.strip()


def sh(*parts: str, timeout: int = 30) -> str:
    """Run one command in the phone's shell with every part quoted."""
    return adb("shell", " ".join(shlex.quote(str(p)) for p in parts), timeout=timeout)


def device() -> str | None:
    """Return the serial of the first connected device, or None."""
    out = adb("devices")
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    return None
