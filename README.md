# PocketPilot

Control your Android phone from the terminal in plain English. You type what you want, [Cactus Needle 3](https://cactuscompute.com/needle) picks the right action, and PocketPilot runs it over adb.

```
❯ battery status
→ battery_status()  (confidence 0.83)
✓ Battery 79%, charging
❯ set brightness to 40%
→ set_brightness_percent(percent=40)  (confidence 0.92)
✓ Brightness set to 40%
❯ dim the screen
? Not sure. Run set_brightness_percent(percent=30)? [Y/n] y
✓ Brightness set to 30%
❯ write me a poem
? Not sure. Run open_file(query='poem')? [Y/n] n
skipped
```

Needle 3 is a 29 MB tool-calling model. It runs locally on your computer, takes about 140 MB of RAM, and needs no API key or internet after the first download.

## What it can do

| Area | Examples |
|---|---|
| Screen | dim, brighten, set brightness to 40%, auto brightness, lock, wake, screenshot |
| Sound | volume to 30%, louder, mute, play/pause, next/previous song |
| Connections | Wi-Fi, Bluetooth, mobile data, flashlight, Do Not Disturb |
| Apps & web | open YouTube, open github.com, search the web, open Wi-Fi settings, go home |
| Photos & files | make an album from last weekend, count yesterday's photos, find/open the lease |
| Clock | set an alarm for 6:30, 10-minute timer |
| Calls & SMS | opens the dialer or an SMS draft. **You tap call/send on the phone.** |
| Info | battery, phone model, storage |

Type `/tools` in the app for the full list.

## Setup

1. On the phone, enable **Developer options** (tap *Build number* 7 times) and turn on **USB debugging**.
2. Install [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) so `adb` is on your PATH.
3. Plug in the phone, accept the "Allow USB debugging" prompt, and check that `adb devices` lists it.
4. Install and run (Python 3.9+):

```sh
pip install git+https://github.com/Tarun91111/pocketpilot
pocketpilot
```

The first run downloads Needle 3 (about 30 MB). You can also run a single command with `pocketpilot turn off wifi`.

### Run the model on the phone

```sh
pocketpilot --on-phone
```

This runs Needle 3 on the phone's own CPU instead of your computer, using Cactus's native Android runner. The first run copies the runner (1.5 MB) and the model (35 MB) to `/data/local/tmp/pocketpilot`. Each start runs the model as a local server on the phone and forwards it over adb. It uses about 75 MB of RAM and answers in roughly 2 seconds on a Galaxy M34. The server stops when you quit. Needs an arm64 phone.

Wireless works too: `adb tcpip 5555`, then `adb connect <phone-ip>:5555`.

### Run everything on the phone (Termux, no PC)

1. Install [Termux](https://github.com/termux/termux-app/releases) (GitHub or F-Droid build, matching your Termux:API if you have it).
2. In Termux: `pkg upgrade -y && pkg install -y python android-tools git`
3. Install PocketPilot:
   ```sh
   git clone https://github.com/Tarun91111/pocketpilot ~/.pocketpilot/src
   cp -r ~/.pocketpilot/src/pocketpilot ~/.pocketpilot/
   install -m 755 ~/.pocketpilot/src/termux/pocketpilot $PREFIX/bin/pocketpilot
   ```
4. Turn on **Settings > Developer options > Wireless debugging**, tap **Pair device with pairing code**, and in Termux (split screen helps) run `adb pair <ip>:<port> <code>`. You only pair once.
5. Run `pocketpilot`. The first time, it asks for the port shown under *IP address & port* on the Wireless debugging screen, and remembers it.

Inside Termux, PocketPilot downloads Cactus's native Android runner and Needle 3 (about 37 MB total) to `~/.pocketpilot` and runs the model on the phone. The `cactus-compute` Python package isn't needed there. The connect port changes when Wireless debugging restarts, so the launcher asks again when the saved one stops working.

## How it works

Each phone action is a Python function in [`pocketpilot/tools.py`](pocketpilot/tools.py) with a plain-English docstring. Needle 3 reads those docstrings, picks one or more functions, and fills in their arguments. PocketPilot runs them with `adb shell`, quoting every argument.

- If Needle isn't sure (confidence below 0.35, or it holds a call back), PocketPilot shows the planned call and asks before running it. Use `-y` or `/yes` to skip the prompt.
- If no tool fits, nothing runs.
- To add an action, write a function with the `@cactus.tool` decorator and a clear docstring.

## Limits

- Some commands depend on the Android version and phone brand. Flashlight needs Android 13+, and toggling Wi-Fi or mobile data is blocked on some phones.
- Needle 3 is a small model. Combined requests like "open github and dim the screen" sometimes get a wrong argument, which is why low-confidence calls are confirmed first.
- Opening a file uses the system Files app, so some file types may open in a picker.

## License

Apache-2.0. Needle 3 and the `cactus-compute` runtime are also Apache-2.0 ([cactus](https://github.com/cactus-compute/cactus), [model card](https://huggingface.co/Cactus-Compute/needle3)). PocketPilot isn't affiliated with Cactus Compute.
