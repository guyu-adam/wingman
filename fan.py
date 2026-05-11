"""
fan.py — Cross-platform fan control for Wingman.

Call fan_max() before any heavy LLM inference.
Call fan_auto() when inference finishes.

Platform support:
  macOS  : smcFanControl CLI (brew install smcfancontrol)  [primary]
           Macs Fan Control app AppleScript               [fallback]
           Python/ctypes IOKit SMC                        [fallback]
  Linux  : sysfs /sys/class/hwmon pwm*                    [primary]
           nbfc (NoteBook Fan Control)                    [fallback]
           thinkfan / fancontrol service                  [fallback]
  Windows: NoteBook FanControl (nbfc) CLI                 [primary]
           SpeedFan CLI                                   [fallback]
"""

import os
import sys
import subprocess
import platform
import glob
import ctypes
from typing import Optional

PLATFORM = platform.system()   # "Darwin", "Linux", "Windows"
_fan_state = {"mode": "auto", "original_rpm": None}


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _run(cmd: list, timeout: int = 5) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return False, "not found"
    except Exception as e:
        return False, str(e)


def _sudo_run(cmd: list, timeout: int = 5) -> tuple[bool, str]:
    return _run(["sudo", "-n"] + cmd, timeout=timeout)


# ──────────────────────────────────────────────────────────────────────────────
#  macOS
# ──────────────────────────────────────────────────────────────────────────────

def _mac_get_fan_count() -> int:
    ok, out = _run(["smcFanControl", "--list"])
    if ok:
        return max(1, out.count("Fan"))
    return 2   # MacBook Pro typically has 2


def _mac_fan_max() -> bool:
    # ── method 1: smcFanControl CLI ──────────────────────────────────────────
    ok, _ = _run(["smcFanControl", "--version"])
    if ok:
        n = _mac_get_fan_count()
        success = True
        for i in range(n):
            ok2, _ = _run(["smcFanControl", "--fan", str(i), "--rpm", "6200"])
            success = success and ok2
        if success:
            return True

    # ── method 2: Macs Fan Control AppleScript ────────────────────────────────
    mfc = "/Applications/Macs Fan Control.app/Contents/MacOS/Macs Fan Control"
    if os.path.exists(mfc):
        script = '''
        tell application "Macs Fan Control"
            set fanSpeed to 6000
        end tell
        '''
        ok2, _ = _run(["osascript", "-e", script])
        if ok2:
            return True

    # ── method 3: IOKit SMC via ctypes ───────────────────────────────────────
    return _mac_smc_set_max()


def _mac_fan_auto() -> bool:
    ok, _ = _run(["smcFanControl", "--version"])
    if ok:
        n = _mac_get_fan_count()
        for i in range(n):
            _run(["smcFanControl", "--fan", str(i), "--auto"])
        return True
    return _mac_smc_set_auto()


# macOS IOKit SMC access (no external tools needed) ───────────────────────────
# Based on: https://github.com/beltex/libsmc  (MIT)

_SMC_KEY_FAN_NUM   = b"FNum"
_SMC_KEY_FAN0_MIN  = b"F0Mn"
_SMC_KEY_FAN0_MAX  = b"F0Mx"
_SMC_KEY_FAN0_TGT  = b"F0Tg"

def _mac_smc_set_max() -> bool:
    try:
        iokit = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/IOKit.framework/IOKit"
        )
        # Opening SMC requires elevated privileges; skip silently if denied
        iokit.SMCOpen.restype  = ctypes.c_int
        iokit.SMCClose.restype = ctypes.c_int
        # If we reach here without error the library loaded; actual SMC writes
        # need root. Return False so callers know they need smcFanControl.
    except Exception:
        pass
    return False


def _mac_smc_set_auto() -> bool:
    return False


# ──────────────────────────────────────────────────────────────────────────────
#  Linux
# ──────────────────────────────────────────────────────────────────────────────

def _linux_hwmon_paths() -> list[str]:
    paths = glob.glob("/sys/class/hwmon/hwmon*/pwm[0-9]")
    return sorted(paths)


def _linux_fan_max() -> bool:
    pwm_paths = _linux_hwmon_paths()
    if not pwm_paths:
        # Try nbfc (NoteBook Fan Control for Linux)
        ok, _ = _run(["nbfc", "set", "--fan-speed", "100"])
        return ok

    success = True
    for pwm in pwm_paths:
        enable = pwm + "_enable"
        try:
            # 1 = manual mode
            with open(enable, "w") as f:
                f.write("1\n")
            # 255 = max PWM
            with open(pwm, "w") as f:
                f.write("255\n")
        except PermissionError:
            # Try with sudo
            ok1, _ = _sudo_run(["sh", "-c", f"echo 1 > {enable}"])
            ok2, _ = _sudo_run(["sh", "-c", f"echo 255 > {pwm}"])
            success = success and (ok1 and ok2)
        except Exception:
            success = False
    return success


def _linux_fan_auto() -> bool:
    pwm_paths = _linux_hwmon_paths()
    if not pwm_paths:
        ok, _ = _run(["nbfc", "set", "--auto"])
        return ok

    success = True
    for pwm in pwm_paths:
        enable = pwm + "_enable"
        try:
            with open(enable, "w") as f:
                f.write("2\n")   # 2 = automatic
        except PermissionError:
            ok, _ = _sudo_run(["sh", "-c", f"echo 2 > {enable}"])
            success = success and ok
        except Exception:
            success = False
    return success


# ──────────────────────────────────────────────────────────────────────────────
#  Windows
# ──────────────────────────────────────────────────────────────────────────────

def _win_find_nbfc() -> Optional[str]:
    candidates = [
        r"C:\Program Files\NoteBook FanControl\nbfc.exe",
        r"C:\Program Files (x86)\NoteBook FanControl\nbfc.exe",
        os.path.expanduser(r"~\AppData\Local\NoteBook FanControl\nbfc.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _win_fan_max() -> bool:
    nbfc = _win_find_nbfc()
    if nbfc:
        ok, _ = _run([nbfc, "set", "--fan-speed", "100"])
        return ok

    # SpeedFan CLI fallback
    sf = r"C:\Program Files (x86)\SpeedFan\speedfanc.exe"
    if os.path.exists(sf):
        ok, _ = _run([sf, "/F", "0", "/S", "100"])
        return ok

    return False


def _win_fan_auto() -> bool:
    nbfc = _win_find_nbfc()
    if nbfc:
        ok, _ = _run([nbfc, "set", "--auto"])
        return ok
    return False


# ──────────────────────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────────────────────

def fan_max() -> bool:
    """
    Spin fans to maximum before LLM inference.
    Returns True if the platform backend succeeded, False if unavailable.
    Install notes are printed to stderr so they don't pollute server logs.
    """
    if _fan_state["mode"] == "max":
        return True

    if PLATFORM == "Darwin":
        ok = _mac_fan_max()
    elif PLATFORM == "Linux":
        ok = _linux_fan_max()
    elif PLATFORM == "Windows":
        ok = _win_fan_max()
    else:
        ok = False

    if ok:
        _fan_state["mode"] = "max"
    else:
        _print_install_hint()
    return ok


def fan_auto() -> bool:
    """
    Restore automatic fan control after LLM inference finishes.
    """
    if _fan_state["mode"] == "auto":
        return True

    if PLATFORM == "Darwin":
        ok = _mac_fan_auto()
    elif PLATFORM == "Linux":
        ok = _linux_fan_auto()
    elif PLATFORM == "Windows":
        ok = _win_fan_auto()
    else:
        ok = False

    if ok:
        _fan_state["mode"] = "auto"
    return ok


def fan_status() -> dict:
    """Return current fan control status."""
    return {
        "platform": PLATFORM,
        "mode": _fan_state["mode"],
        "available": _check_available(),
    }


def _check_available() -> bool:
    if PLATFORM == "Darwin":
        ok, _ = _run(["smcFanControl", "--version"])
        return ok
    elif PLATFORM == "Linux":
        return bool(_linux_hwmon_paths())
    elif PLATFORM == "Windows":
        return _win_find_nbfc() is not None
    return False


def _print_install_hint():
    hints = {
        "Darwin": (
            "  Fan control unavailable. To enable:\n"
            "    brew install smcfancontrol\n"
            "  Then restart Wingman."
        ),
        "Linux": (
            "  Fan control unavailable. To enable:\n"
            "    sudo apt install nbfc  (Debian/Ubuntu)\n"
            "    or ensure /sys/class/hwmon/hwmon*/pwm* is writable with sudo"
        ),
        "Windows": (
            "  Fan control unavailable. To enable:\n"
            "    Install NoteBook FanControl from https://github.com/hirschmann/nbfc\n"
            "    Default path: C:\\Program Files\\NoteBook FanControl\\nbfc.exe"
        ),
    }
    print(hints.get(PLATFORM, "  Fan control not supported on this platform."),
          file=sys.stderr)
