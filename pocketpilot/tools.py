"""Phone actions exposed to Needle 3 as tools.

Needle reads each function's name, type hints and docstring, so the docstrings
are written as the plain-English requests a user would type. Tools take simple
arguments (percent, "last weekend") rather than raw device values, which the
model fills more reliably.
"""

from __future__ import annotations

from datetime import datetime

import cactus

from .adb import adb, sh
from .periods import parse_period

PHOTO_DIRS = ["/sdcard/DCIM", "/sdcard/Pictures"]
MEDIA_EXT = (".jpg", ".jpeg", ".png", ".heic", ".webp", ".mp4", ".mov")
FILE_DIRS = ["/sdcard/Download", "/sdcard/Documents", "/sdcard/DCIM", "/sdcard/Pictures"]


def _brightness(percent: int) -> str:
    percent = max(0, min(100, int(percent)))
    sh("settings", "put", "system", "screen_brightness_mode", "0")
    sh("settings", "put", "system", "screen_brightness", str(round(percent * 2.55)))
    return f"Brightness set to {percent}%"


def _current_brightness_pct() -> int:
    return round(int(sh("settings", "get", "system", "screen_brightness")) / 2.55)


# --- screen ------------------------------------------------------------------

@cactus.tool
def dim_screen():
    "Dim the screen, lower the brightness, make it darker."
    return _brightness(max(5, _current_brightness_pct() - 30))


@cactus.tool
def brighten_screen():
    "Make the screen brighter, raise the brightness."
    return _brightness(min(100, _current_brightness_pct() + 30))


@cactus.tool
def set_brightness_percent(percent: int):
    "Set screen brightness to an exact percent the user says, 0 to 100."
    return _brightness(percent)


@cactus.tool
def auto_brightness(enabled: bool):
    "Turn adaptive (automatic) brightness on or off."
    sh("settings", "put", "system", "screen_brightness_mode", "1" if enabled else "0")
    return f"Auto brightness {'on' if enabled else 'off'}"


@cactus.tool
def lock_screen():
    "Lock the phone, turn the screen off."
    sh("input", "keyevent", "223")
    return "Screen locked"


@cactus.tool
def wake_screen():
    "Wake the phone, turn the screen on."
    sh("input", "keyevent", "224")
    return "Screen on"


@cactus.tool
def take_screenshot():
    "Take a screenshot of the phone and save it on the computer."
    name = datetime.now().strftime("screenshot_%Y%m%d_%H%M%S.png")
    with open(name, "wb") as f:
        f.write(adb("exec-out", "screencap", "-p", binary=True))
    return f"Saved {name}"


# --- sound & media -------------------------------------------------------------

@cactus.tool
def set_volume_percent(percent: int):
    "Set the media/music volume to a percent, 0 to 100."
    out = sh("cmd", "media_session", "volume", "--stream", "3", "--get")
    # Output looks like "volume is 7 in range [0..15]"
    top = 15
    if "[0.." in out:
        top = int(out.split("[0..")[1].split("]")[0])
    level = round(max(0, min(100, int(percent))) / 100 * top)
    sh("cmd", "media_session", "volume", "--stream", "3", "--set", str(level))
    return f"Volume set to {percent}%"


@cactus.tool
def volume_up():
    "Turn the volume up, louder."
    sh("input", "keyevent", "24")
    return "Volume up"


@cactus.tool
def volume_down():
    "Turn the volume down, quieter."
    sh("input", "keyevent", "25")
    return "Volume down"


@cactus.tool
def mute():
    "Mute the phone sound."
    sh("input", "keyevent", "164")
    return "Muted"


@cactus.tool
def play_pause_music():
    "Play or pause the music or video that is playing."
    sh("input", "keyevent", "85")
    return "Play/pause sent"


@cactus.tool
def next_track():
    "Skip to the next song or track."
    sh("input", "keyevent", "87")
    return "Next track"


@cactus.tool
def previous_track():
    "Go back to the previous song or track."
    sh("input", "keyevent", "88")
    return "Previous track"


# --- connectivity --------------------------------------------------------------

@cactus.tool
def set_wifi(enabled: bool):
    "Turn Wi-Fi on or off."
    sh("svc", "wifi", "enable" if enabled else "disable")
    return f"Wi-Fi {'on' if enabled else 'off'}"


@cactus.tool
def set_bluetooth(enabled: bool):
    "Turn Bluetooth on or off."
    sh("cmd", "bluetooth_manager", "enable" if enabled else "disable")
    return f"Bluetooth {'on' if enabled else 'off'}"


@cactus.tool
def set_mobile_data(enabled: bool):
    "Turn mobile data on or off."
    sh("svc", "data", "enable" if enabled else "disable")
    return f"Mobile data {'on' if enabled else 'off'}"


@cactus.tool
def set_flashlight(enabled: bool):
    "Turn the flashlight / torch on or off."
    sh("cmd", "statusbar", "torch", "on" if enabled else "off")
    return f"Flashlight {'on' if enabled else 'off'}"


@cactus.tool
def set_do_not_disturb(enabled: bool):
    "Turn Do Not Disturb (silence notifications) on or off."
    sh("cmd", "notification", "set_dnd", "priority" if enabled else "off")
    return f"Do Not Disturb {'on' if enabled else 'off'}"


# --- apps & web ----------------------------------------------------------------

@cactus.tool
def open_website(url: str):
    "Open a website or web page in the phone browser."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    sh("am", "start", "-a", "android.intent.action.VIEW", "-d", url)
    return f"Opened {url}"


@cactus.tool
def search_web(query: str):
    "Search the web / Google for something."
    sh("am", "start", "-a", "android.intent.action.WEB_SEARCH", "--es", "query", query)
    return f"Searched for '{query}'"


@cactus.tool
def open_app(app_name: str):
    "Open an app on the phone by its name, e.g. WhatsApp, camera, YouTube."
    return _launch(app_name)


def _launch(app_name: str) -> str:
    name = app_name.lower().replace(" ", "")
    if "." in name and not name.startswith("com."):  # "github.com" is a site, not an app
        return open_website(app_name)
    aliases = {"camera": "android.media.action.STILL_IMAGE_CAMERA",
               "settings": "android.settings.SETTINGS"}
    if name in aliases:
        sh("am", "start", "-a", aliases[name])
        return f"Opened {app_name}"
    pkgs = [l.removeprefix("package:") for l in sh("pm", "list", "packages").splitlines()]
    matches = [p for p in pkgs if name in p.lower().replace(".", "")]
    if not matches:
        return f"No app matching '{app_name}'"
    pkg = min(matches, key=len)  # shortest match is usually the main app
    sh("monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    return f"Opened {app_name} ({pkg})"


@cactus.tool
def go_home():
    "Go to the home screen."
    sh("input", "keyevent", "3")
    return "Home screen"


@cactus.tool
def open_settings_page(page: str):
    "Open a settings page: wifi, bluetooth, display, sound, battery, apps, location."
    pages = {"wifi": "WIFI_SETTINGS", "bluetooth": "BLUETOOTH_SETTINGS",
             "display": "DISPLAY_SETTINGS", "sound": "SOUND_SETTINGS",
             "battery": "BATTERY_SAVER_SETTINGS", "apps": "APPLICATION_SETTINGS",
             "location": "LOCATION_SOURCE_SETTINGS"}
    key = page.lower().replace("-", "").replace(" ", "")
    action = pages.get(key, "SETTINGS")
    sh("am", "start", "-a", f"android.settings.{action}")
    return f"Opened {page} settings"


# --- photos & files -------------------------------------------------------------

def _media_between(start: datetime, end: datetime) -> list[str]:
    out = sh("find", *PHOTO_DIRS, "-type", "f", "-not", "-path", "*/.*",
             "-exec", "stat", "-c", "%Y|%n", "{}", "+", timeout=60)
    s, e = start.timestamp(), end.timestamp()
    hits = []
    for line in out.splitlines():
        ts, _, path = line.partition("|")
        if path.lower().endswith(MEDIA_EXT) and ts.isdigit() and s <= int(ts) < e:
            hits.append(path)
    return sorted(hits)


@cactus.tool
def count_photos(period: str):
    "Count photos taken in a period like 'today', 'yesterday', 'last weekend', 'last 7 days'."
    start, end = parse_period(period)
    n = len(_media_between(start, end))
    return f"{n} photos/videos from {period} ({start:%a %d %b} to {end:%a %d %b})"


@cactus.tool
def make_album(name: str, period: str):
    "Make a photo album from photos taken in a period like 'last weekend', 'yesterday', 'last 3 days'."
    start, end = parse_period(period)
    files = _media_between(start, end)
    if not files:
        return f"No photos from {period} ({start:%d %b} to {end:%d %b})"
    safe = "".join(c for c in name if c.isalnum() or c in " -_").strip() or "Album"
    dest = f"/sdcard/Pictures/{safe}"
    sh("mkdir", "-p", dest)
    sh("cp", "-p", *files, dest, timeout=300)
    # Ask the media scanner to index the new folder so the gallery shows it.
    for f in files:
        base = f.rsplit("/", 1)[1]
        sh("am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
           "-d", f"file://{dest}/{base}")
    return f"Album '{safe}' made with {len(files)} items in Pictures/{safe}"


@cactus.tool
def find_files(query: str):
    "Find a file or document on the phone by name, e.g. lease, resume, ticket."
    out = sh("find", *FILE_DIRS, "-type", "f", "-iname", f"*{query}*", timeout=60)
    hits = [l for l in out.splitlines() if l][:20]
    if not hits:
        return f"No files matching '{query}'"
    return f"Found {len(hits)}:\n" + "\n".join("  " + h for h in hits)


@cactus.tool
def open_file(query: str):
    "Open a file on the phone by name, e.g. open the lease PDF."
    out = sh("find", *FILE_DIRS, "-type", "f", "-iname", f"*{query}*", timeout=60)
    hits = [l for l in out.splitlines() if l]
    if not hits:
        return f"No files matching '{query}'"
    path = hits[0]
    ext = path.rsplit(".", 1)[-1].lower()
    mime = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "mp4": "video/mp4", "txt": "text/plain",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }.get(ext, "*/*")
    # file:// URIs are blocked for apps on modern Android; the Files app handles content.
    sh("am", "start", "-a", "android.intent.action.VIEW", "-t", mime, "-d",
       "content://com.android.externalstorage.documents/document/primary%3A"
       + path.removeprefix("/sdcard/").replace("/", "%2F"))
    return f"Opened {path}"


# --- calls, messages, alarms (open the app; you tap send/call) --------------------

@cactus.tool
def call_number(number: str):
    "Open the dialer with a phone number ready to call."
    sh("am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{number}")
    return f"Dialer ready with {number}. Tap call on the phone."


@cactus.tool
def text_message(number: str, message: str):
    "Write an SMS text message to a phone number."
    sh("am", "start", "-a", "android.intent.action.SENDTO", "-d", f"sms:{number}",
       "--es", "sms_body", message)
    return f"SMS draft to {number} open. Tap send on the phone."


@cactus.tool
def set_alarm(hour: int, minute: int):
    "Set an alarm for a time, hour in 24-hour format."
    sh("am", "start", "-a", "android.intent.action.SET_ALARM",
       "--ei", "android.intent.extra.alarm.HOUR", str(int(hour)),
       "--ei", "android.intent.extra.alarm.MINUTES", str(int(minute)),
       "--ez", "android.intent.extra.alarm.SKIP_UI", "true")
    return f"Alarm set for {int(hour):02d}:{int(minute):02d}"


@cactus.tool
def set_timer(minutes: int):
    "Start a countdown timer for some minutes."
    sh("am", "start", "-a", "android.intent.action.SET_TIMER",
       "--ei", "android.intent.extra.alarm.LENGTH", str(int(minutes) * 60),
       "--ez", "android.intent.extra.alarm.SKIP_UI", "true")
    return f"Timer set for {minutes} min"


# --- info -----------------------------------------------------------------------

@cactus.tool
def battery_status():
    "Check the battery level and whether the phone is charging."
    info = {}
    for line in sh("dumpsys", "battery").splitlines():
        key, sep, val = line.strip().partition(": ")
        if sep:
            info.setdefault(key, val)
    charging = "charging" if info.get("status") == "2" else "not charging"
    return f"Battery {info.get('level', '?')}%, {charging}"


@cactus.tool
def device_info():
    "Show the phone model, Android version and storage space."
    model = sh("getprop", "ro.product.model")
    ver = sh("getprop", "ro.build.version.release")
    df = sh("df", "-h", "/sdcard").splitlines()[-1].split()
    return f"{model}, Android {ver}, storage {df[2]} used of {df[1]} ({df[4]})"


ALL_TOOLS = [v for v in list(globals().values())
             if callable(v) and getattr(v, "__module__", None) == __name__
             and not getattr(v, "__name__", "_").startswith("_")
             and v.__name__ not in ("adb", "sh", "parse_period")]
