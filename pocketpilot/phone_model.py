"""Run Needle 3 on the phone itself instead of on the computer.

Cactus publishes a native Android runner (`cactus`, android-arm64) that can
serve Needle 3 over HTTP. Two cases:

- From a PC: push the runner, weights and tool list to /data/local/tmp over
  adb, start the server there and forward its port.
- Inside Termux on the phone: keep everything in ~/.pocketpilot and start the
  server as a normal child process.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from .adb import AdbError, adb, sh

ON_ANDROID = bool(os.environ.get("ANDROID_ROOT") and os.environ.get("ANDROID_DATA"))
REMOTE = "/data/local/tmp/pocketpilot"
PORT = 8765
RUNNER_URL = ("https://huggingface.co/Cactus-Compute/cactus/resolve/main/"
              "releases/4.0.0/android-arm64/cactus")
WEIGHTS_URL = "https://huggingface.co/Cactus-Compute/needle3/resolve/main/needle3.cact"
CACHE = Path.home() / (".pocketpilot" if ON_ANDROID else ".cache/pocketpilot")


def _post(path: str, body: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _download(url: str, dest: Path, label: str) -> Path:
    if not dest.exists():
        print(f"Downloading {label} …")
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
    return dest


def _runner() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    name = "cactus" if ON_ANDROID else "cactus-android-arm64"
    path = _download(RUNNER_URL, CACHE / name, "the Android Needle runner (1.5 MB)")
    if ON_ANDROID:
        path.chmod(0o755)
    return path


def _weights() -> Path:
    if ON_ANDROID:
        CACHE.mkdir(parents=True, exist_ok=True)
        return _download(WEIGHTS_URL, CACHE / "needle3.cact", "Needle 3 (35 MB)")
    from huggingface_hub import hf_hub_download
    return Path(hf_hub_download("Cactus-Compute/needle3", "needle3.cact"))


def _wait_ready(log: str) -> None:
    for _ in range(60):
        try:
            _post("/reset", timeout=2)
            return
        except OSError:
            time.sleep(0.25)
    raise AdbError("Needle server didn't start. Log:\n" + log)


class PhoneNeedle:
    """Same .complete(text) interface as cactus.Cactus, but runs on the phone."""

    def __init__(self, tools: list):
        self.tools_json = json.dumps([t._cactus_tool for t in tools], indent=1)
        self.proc: subprocess.Popen | None = None

    # --- inside Termux ---------------------------------------------------------

    def _start_local(self):
        runner, weights = _runner(), _weights()
        tools = CACHE / "tools.json"
        tools.write_text(self.tools_json, encoding="utf-8")
        logf = open(CACHE / "server.log", "w")
        self.proc = subprocess.Popen(
            [str(runner), "--model", str(weights), "--tools", str(tools),
             "--serve", "--port", str(PORT)],
            stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=CACHE)
        try:
            _wait_ready("")
        except AdbError:
            self.proc.kill()
            raise AdbError("Needle server didn't start. Log:\n"
                           + (CACHE / "server.log").read_text(errors="replace"))

    # --- from a PC over adb ------------------------------------------------------

    def _start_remote(self):
        abi = sh("getprop", "ro.product.cpu.abi")
        if abi != "arm64-v8a":
            raise AdbError(f"On-phone mode needs an arm64 phone, this one is {abi}")
        sh("mkdir", "-p", REMOTE)
        files = sh("ls", REMOTE).split()
        if "cactus" not in files:
            adb("push", str(_runner()), f"{REMOTE}/cactus")
            sh("chmod", "755", f"{REMOTE}/cactus")
        if "needle3.cact" not in files:
            print("Copying Needle 3 to the phone (35 MB) …")
            adb("push", str(_weights()), f"{REMOTE}/needle3.cact", timeout=300)
        local = CACHE / "tools.json"
        CACHE.mkdir(parents=True, exist_ok=True)
        local.write_text(self.tools_json, encoding="utf-8")
        adb("push", str(local), f"{REMOTE}/tools.json")

        self._stop_remote()  # restart so it loads the current tools.json
        adb("shell", f"cd {REMOTE} && (nohup ./cactus --model needle3.cact "
                     f"--tools tools.json --serve --port {PORT} >server.log 2>&1 & "
                     f"echo $! > server.pid)")
        adb("forward", f"tcp:{PORT}", f"tcp:{PORT}")
        try:
            _wait_ready("")
        except AdbError:
            raise AdbError("Needle server didn't start on the phone. Log:\n"
                           + sh("cat", f"{REMOTE}/server.log"))

    @staticmethod
    def _stop_remote():
        # Kill by saved PID. (pkill -f would match this adb shell's own command line.)
        adb("shell", f"[ -f {REMOTE}/server.pid ] && kill $(cat {REMOTE}/server.pid) "
                     f"2>/dev/null; rm -f {REMOTE}/server.pid; true")

    # --- common --------------------------------------------------------------------

    def __enter__(self):
        if ON_ANDROID:
            self._start_local()
        else:
            self._start_remote()
        return self

    def complete(self, text: str) -> dict:
        _post("/reset")  # one command per turn, like stateless=True
        return _post("/complete", {"input": text})

    def __exit__(self, *exc):
        try:
            if self.proc:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            else:
                self._stop_remote()
                adb("forward", "--remove", f"tcp:{PORT}")
        except (AdbError, subprocess.TimeoutExpired):
            pass
        return False
