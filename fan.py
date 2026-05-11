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

MFC_APP      = "/Applications/Macs Fan Control.app/Contents/MacOS/Macs Fan Control"
MFC_BUNDLE   = "com.crystalidea.macsfancontrol"
MFC_MAX_RPM  = "6200"   # safe max for most MacBook Pro fans

# Saves original settings so fan_auto() can restore them
_mac_saved: dict = {}


def _mfc_installed() -> bool:
    return os.path.exists(MFC_APP)


def _mfc_running() -> bool:
    ok, _ = _run(["pgrep", "-f", "Macs Fan Control"])
    return ok


def _mfc_write_pref(key: str, value: str):
    subprocess.run(["defaults", "write", MFC_BUNDLE, key, value],
                   capture_output=True, timeout=3)


def _mfc_reload():
    """Kill app if running then reopen via 'open -a' so it picks up new defaults."""
    subprocess.run(["pkill", "-f", "Macs Fan Control"], capture_output=True, timeout=3)
    import time; time.sleep(0.5)
    subprocess.Popen(["open", "-a", "Macs Fan Control"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)   # give it time to read prefs and connect to SMC


def _mac_fan_max() -> bool:
    # ── method 1: smcFanControl CLI (brew install smcfancontrol) ─────────────
    ok, _ = _run(["smcFanControl", "--version"])
    if ok:
        for i in range(2):
            _run(["smcFanControl", "--fan", str(i), "--rpm", MFC_MAX_RPM])
        return True

    # ── method 2: Macs Fan Control via defaults + app launch ─────────────────
    if _mfc_installed():
        try:
            import subprocess as _sp, time as _t
            # Save current prefs before overwriting
            result = _sp.run(["defaults", "read", MFC_BUNDLE],
                             capture_output=True, text=True, timeout=3)
            _mac_saved["raw_prefs"] = result.stdout
            _mac_saved["Fan_0"]     = _sp.run(
                ["defaults", "read", MFC_BUNDLE, "Fan_0"],
                capture_output=True, text=True, timeout=2).stdout.strip()
            _mac_saved["Fan_1"]     = _sp.run(
                ["defaults", "read", MFC_BUNDLE, "Fan_1"],
                capture_output=True, text=True, timeout=2).stdout.strip()
            _mac_saved["ActivePreset"] = _sp.run(
                ["defaults", "read", MFC_BUNDLE, "ActivePreset"],
                capture_output=True, text=True, timeout=2).stdout.strip()
        except Exception:
            pass

        _mfc_write_pref("Fan_0", f"1,{MFC_MAX_RPM}")
        _mfc_write_pref("Fan_1", f"1,{MFC_MAX_RPM}")
        _mfc_write_pref("ActivePreset", "Custom")
        _mfc_reload()
        return True

    return False


def _mac_fan_auto() -> bool:
    # ── method 1: smcFanControl CLI ──────────────────────────────────────────
    ok, _ = _run(["smcFanControl", "--version"])
    if ok:
        for i in range(2):
            _run(["smcFanControl", "--fan", str(i), "--auto"])
        return True

    # ── method 2: restore saved MFC prefs ────────────────────────────────────
    if _mfc_installed():
        # Restore previously saved values; fall back to OS-auto (preset 0)
        fan0 = _mac_saved.get("Fan_0", "0")
        fan1 = _mac_saved.get("Fan_1", "0")
        preset = _mac_saved.get("ActivePreset", "Predefined:0")

        _mfc_write_pref("Fan_0", fan0 if fan0 else "0")
        _mfc_write_pref("Fan_1", fan1 if fan1 else "0")
        _mfc_write_pref("ActivePreset", preset if preset else "Predefined:0")
        _mfc_reload()
        return True

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
        if ok:
            return True
        return _mfc_installed()   # Macs Fan Control app also works
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
