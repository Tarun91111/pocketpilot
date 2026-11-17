"""Run Needle 3 on the phone itself instead of on the computer.

Cactus publishes a native Android runner (`cactus`, android-arm64). This module
pushes it, the model weights and the tool list to /data/local/tmp/pocketpilot,
starts it as an HTTP server on the phone, and forwards the port over adb.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

from .adb import AdbError, adb, sh

REMOTE = "/data/local/tmp/pocketpilot"
PORT = 8765
RUNNER_URL = ("https://huggingface.co/Cactus-Compute/cactus/resolve/main/"
              "releases/4.0.0/android-arm64/cactus")
CACHE = Path.home() / ".cache" / "pocketpilot"


def _post(path: str, body: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _runner() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "cactus-android-arm64"
    if not path.exists():
        print("Downloading the Android Needle runner (1.5 MB) …")
        urllib.request.urlretrieve(RUNNER_URL, path)
    return path


def _weights() -> Path:
    from huggingface_hub import hf_hub_download
    return Path(hf_hub_download("Cactus-Compute/needle3", "needle3.cact"))


class PhoneNeedle:
    """Same .complete(text) interface as cactus.Cactus, but runs on the phone."""

    def __init__(self, tools: list):
        self.tools_json = json.dumps([t._cactus_tool for t in tools], indent=1)

    def __enter__(self):
        abi = sh("getprop", "ro.product.cpu.abi")
        if abi != "arm64-v8a":
            raise AdbError(f"On-phone mode needs an arm64 phone, this one is {abi}")
        sh("mkdir", "-p", REMOTE)
        # Push only what is missing or changed.
        if sh("ls", REMOTE).split().count("cactus") == 0:
            adb("push", str(_runner()), f"{REMOTE}/cactus")
            sh("chmod", "755", f"{REMOTE}/cactus")
        if "needle3.cact" not in sh("ls", REMOTE).split():
            print("Copying Needle 3 to the phone (35 MB) …")
            adb("push", str(_weights()), f"{REMOTE}/needle3.cact", timeout=300)
        local = CACHE / "tools.json"
        CACHE.mkdir(parents=True, exist_ok=True)
        local.write_text(self.tools_json, encoding="utf-8")
        adb("push", str(local), f"{REMOTE}/tools.json")

        # Restart the server so it loads the current tools.json.
        self.close_server()
        adb("shell", f"cd {REMOTE} && (nohup ./cactus --model needle3.cact "
                     f"--tools tools.json --serve --port {PORT} >server.log 2>&1 & "
                     f"echo $! > server.pid)")
        adb("forward", f"tcp:{PORT}", f"tcp:{PORT}")
        for _ in range(40):
            try:
                _post("/reset", timeout=2)
                return self
            except OSError:
                time.sleep(0.25)
        raise AdbError("Needle server didn't start on the phone. Log:\n"
                       + sh("cat", f"{REMOTE}/server.log"))

    def complete(self, text: str) -> dict:
        _post("/reset")  # one command per turn, like stateless=True
        return _post("/complete", {"input": text})

    @staticmethod
    def close_server():
        # Kill by saved PID. (pkill -f would match this adb shell's own command line.)
        adb("shell", f"[ -f {REMOTE}/server.pid ] && kill $(cat {REMOTE}/server.pid) "
                     f"2>/dev/null; rm -f {REMOTE}/server.pid; true")

    def __exit__(self, *exc):
        try:
            self.close_server()
            adb("forward", "--remove", f"tcp:{PORT}")
        except AdbError:
            pass
        return False
