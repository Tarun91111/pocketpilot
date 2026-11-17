"""PocketPilot terminal: type what you want, Needle 3 picks the phone action."""

from __future__ import annotations

import argparse
import os
import sys
import warnings

os.environ.setdefault("CACTUS_TELEMETRY", "0")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
warnings.filterwarnings("ignore")
# Windows consoles may default to cp1252, which can't print ✓ or →.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from . import __version__  # noqa: E402
from .adb import AdbError, device, sh  # noqa: E402

GREEN, YELLOW, RED, DIM, BOLD, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m")
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    GREEN = YELLOW = RED = DIM = BOLD = RESET = ""

ASK_BELOW = 0.35  # confirm calls the model is less sure about than this

HELP = f"""{BOLD}Talk to your phone in plain English.{RESET} Examples:
  dim the screen              set brightness to 40%
  open github.com             turn off wifi
  make an album called Goa from last weekend's photos
  find the lease in my files  set an alarm for 6:30
  battery status              open youtube

{BOLD}Commands:{RESET}
  /tools      list everything PocketPilot can do
  /yes        always run low-confidence calls without asking (toggle)
  /adb <cmd>  run a raw adb shell command
  /help       show this
  /quit       exit (or Ctrl+C)
"""


def _fmt_call(c: dict) -> str:
    args = ", ".join(f"{k}={v!r}" for k, v in c.get("arguments", {}).items())
    return f"{c['name']}({args})"


def _run_calls(calls: list[dict], by_name: dict) -> None:
    for c in calls:
        fn = by_name.get(c["name"])
        if fn is None:
            print(f"{RED}✗ unknown tool {c['name']}{RESET}")
            continue
        try:
            result = fn(**c.get("arguments", {}))
            print(f"{GREEN}✓ {result}{RESET}")
        except Exception as e:  # report and keep the session alive

            print(f"{RED}✗ {c['name']} failed: {e}{RESET}")


def handle(agent, text: str, by_name: dict, state: dict) -> None:
    # complete() proposes calls without running them, so we decide what runs.
    r = agent.complete(text)
    calls = r.get("function_calls") or []
    held = r.get("suppressed_calls") or []
    conf = r.get("confidence") or 0.0
    if state["debug"]:
        print(f"{DIM}{r}{RESET}")

    # Needle holds back calls it isn't sure about, and low-confidence calls are
    # often a wrong guess ("write me a poem" -> open_file). Show them and ask.
    if not calls and held or calls and conf < ASK_BELOW:
        calls = calls or held
        plan = "  then  ".join(_fmt_call(c) for c in calls)
        if not state["auto_yes"]:
            try:
                ans = input(f"{YELLOW}? Not sure. Run {plan}? [Y/n] {RESET}").strip().lower()
            except EOFError:
                ans = "n"
            if ans not in ("", "y", "yes"):
                print(f"{DIM}skipped{RESET}")
                return
    if not calls:
        print(f"{YELLOW}• I can't do that on the phone yet. Type /tools to see what I can do.{RESET}")
        return
    print(f"{DIM}→ {'  then  '.join(_fmt_call(c) for c in calls)}  (confidence {conf:.2f}){RESET}")
    _run_calls(calls, by_name)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pocketpilot", description=__doc__)
    p.add_argument("command", nargs="*", help="run one command and exit")
    p.add_argument("-y", "--yes", action="store_true",
                   help="run low-confidence calls without asking")
    p.add_argument("--debug", action="store_true", help="print raw model output")
    p.add_argument("--on-phone", action="store_true",
                   help="run Needle 3 on the phone's CPU instead of this computer")
    p.add_argument("--version", action="version", version=f"pocketpilot {__version__}")
    a = p.parse_args(argv)

    try:
        serial = device()
    except AdbError as e:
        print(f"{RED}{e}{RESET}")
        return 1
    if not serial:
        print(f"{RED}No phone found. Plug it in, enable USB debugging, accept the prompt, "
              f"then check `adb devices`.{RESET}")
        return 1
    os.environ["ANDROID_SERIAL"] = serial
    model = sh("getprop", "ro.product.model")

    print(f"{DIM}Loading Needle 3 …{RESET}", end="\r", flush=True)
    from .phone_model import ON_ANDROID
    if ON_ANDROID:
        a.on_phone = True  # Termux: no cactus wheel, use the native runner
    from .tools import ALL_TOOLS
    by_name = {t.__name__: t for t in ALL_TOOLS}
    state = {"auto_yes": a.yes, "debug": a.debug}
    print("\r" + " " * 24 + "\r", end="", flush=True)  # clear "Loading" line

    system = ("You control an Android phone. Pick the tools that do what the user asks. "
              "If no tool fits, call none.")
    if a.on_phone:
        from .phone_model import PhoneNeedle
        engine = PhoneNeedle(ALL_TOOLS)
        where = "Needle 3 running on the phone"
    else:
        import cactus
        engine = cactus.Cactus(tools=ALL_TOOLS, system=system, stateless=True)
        where = "Needle 3 on this computer"
    with engine as agent:
        if a.command:
            handle(agent, " ".join(a.command), by_name, state)
            return 0

        print(f"{BOLD}PocketPilot {__version__}{RESET} · {model} ({serial}) · "
              f"{where} · /help")
        while True:
            try:
                text = input(f"{BOLD}❯ {RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not text:
                continue
            if text in ("/quit", "/exit", "exit", "quit"):
                return 0
            if text == "/help":
                print(HELP)
            elif text == "/tools":
                for t in ALL_TOOLS:
                    doc = (t.__doc__ or "").strip().splitlines()[0]
                    print(f"  {BOLD}{t.__name__:<24}{RESET}{doc}")
            elif text == "/yes":
                state["auto_yes"] = not state["auto_yes"]
                print(f"auto-run {'on' if state['auto_yes'] else 'off'}")
            elif text.startswith("/adb "):
                try:
                    from .adb import adb
                    print(adb("shell", text[5:]))
                except AdbError as e:
                    print(f"{RED}{e}{RESET}")
            else:
                try:
                    handle(agent, text, by_name, state)
                except KeyboardInterrupt:
                    print(f"{DIM}cancelled{RESET}")


if __name__ == "__main__":
    sys.exit(main())
