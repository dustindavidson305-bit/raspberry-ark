#!/usr/bin/env python3
"""
Builds Raspberry-Ark-Setup.py — the universal installer for
The Raspberry Ark.

The Setup file is a single self-contained Python program. Both halves
of the app (the desktop SD-prep/flash tool and the on-Pi RetroArch
installer) plus the emblem are embedded in it as one compressed
payload. Run it anywhere:

  * On Windows / macOS / Linux it installs the DESKTOP half (SD prep
    + Pi OS flash + first-boot staging).
  * On a Raspberry Pi running Raspberry Pi OS it installs the PI half
    (the `raspberry-ark-pi` command) and offers to run the RetroArch
    installation right away.

Usage:  python3 build_installer.py
"""

import base64
import io
import zipfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "Raspberry-Ark-Setup.py"
FILES = ["raspberry_ark.py", "raspberry_ark_pi.py", "assets/emblem.png"]

TEMPLATE = r'''#!/usr/bin/env python3
# The Raspberry Ark - universal installer (Windows / macOS / Linux /
# Raspberry Pi OS).
#
# One file: it detects the machine it is running on and installs the
# matching half of The Raspberry Ark. On a desktop it installs the
# SD-prep + flash + staging tool; on a Raspberry Pi it installs the
# RetroArch installer app. Both halves and the emblem are embedded
# below as a compressed payload; nothing else is needed.
#
#   Install:    python3 Raspberry-Ark-Setup.py [--yes]
#   Uninstall:  python3 Raspberry-Ark-Setup.py --uninstall
# (On Windows use "py -3" instead of "python3". Python 3.9+ required.)

import base64
import io
import os
import platform
import shutil
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

APP_NAME = "The Raspberry Ark"
APP_VERSION = "1.0.0"
DESKTOP_FILE = "raspberry_ark.py"
PI_FILE = "raspberry_ark_pi.py"
PUBLISHER = "Delukz"

PAYLOAD_B64 = "@@PAYLOAD@@"

SD_NOTE = ("SD / microSD card required for flashing: 8 GB minimum, "
           "16 GB recommended (the app shows the exact size for the "
           "image you pick).")


def payload_files():
    raw = zlib.decompress(base64.b64decode(PAYLOAD_B64))
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return {name: z.read(name) for name in z.namelist()}


def detect_os():
    s = platform.system().lower()
    if s.startswith("win"):
        return "windows"
    if s == "darwin":
        return "macos"
    return "linux"


def detect_pi():
    try:
        if Path("/etc/rpi-issue").exists():
            return True
        model = Path("/proc/device-tree/model").read_text(
            errors="replace")
        return "raspberry pi" in model.lower()
    except OSError:
        return False


def os_label(os_id):
    return {"windows": "Windows", "macos": "macOS",
            "linux": "Linux"}[os_id]


def locations(os_id):
    home = Path.home()
    if os_id == "windows":
        root = Path(os.environ.get("LOCALAPPDATA",
                                   home / "AppData" / "Local"))
        base = root / "The-Raspberry-Ark"
    elif os_id == "macos":
        base = home / "Applications" / "The-Raspberry-Ark"
    else:
        base = home / ".local" / "share" / "raspberry-ark"
    return home, base


def make_executable(path):
    try:
        os.chmod(path, os.stat(path).st_mode | 0o111)
    except OSError:
        pass


def write_payload(base, names):
    files = payload_files()
    written = {}
    for name in names:
        dest = base / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(files[name])
        written[name] = dest
    return written


def link_command(home, base, app_path, cmd_name, desktop_name, comment):
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / cmd_name
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(app_path, link)
    except OSError:
        link.write_text('#!/bin/sh\nexec python3 "' + str(app_path)
                        + '" "$@"\n', encoding="utf-8")
        make_executable(link)
    apps_dir = home / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    (apps_dir / (cmd_name + ".desktop")).write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=" + desktop_name + "\n"
        "Comment=" + comment + "\n"
        "Exec=" + str(app_path) + "\n"
        "Icon=" + str(base / "assets" / "emblem.png") + "\n"
        "Terminal=true\n"
        "Categories=Utility;\n", encoding="utf-8")


# ------------------------------------------------------------- Pi install
def install_pi(home, base):
    written = write_payload(base, [PI_FILE, "assets/emblem.png"])
    app = written[PI_FILE]
    make_executable(app)
    link_command(home, base, app, "raspberry-ark-pi",
                 "The Raspberry Ark",
                 "Install RetroArch on your Raspberry Pi")
    print()
    print("Pi app installed to " + str(base))
    print("Checking this Pi:")
    print()
    sys.stdout.flush()
    det = subprocess.run([sys.executable, str(app), "detect"])
    print()
    run_now = "--yes" in sys.argv
    if not run_now and sys.stdin.isatty():
        try:
            run_now = input("Install RetroArch now? [Y/n]: ") \
                .strip().lower() in ("", "y", "yes")
        except EOFError:
            run_now = False
    if run_now:
        print()
        return subprocess.run([sys.executable, str(app),
                               "install"]).returncode
    print("When you're ready:  raspberry-ark-pi install")
    return 0 if det.returncode in (0, 2) else det.returncode


# -------------------------------------------------------- desktop: Linux
def install_linux(home, base):
    written = write_payload(base, [DESKTOP_FILE, PI_FILE,
                                   "assets/emblem.png"])
    app = written[DESKTOP_FILE]
    make_executable(app)
    make_executable(written[PI_FILE])
    link_command(home, base, app, "raspberry-ark", "The Raspberry Ark",
                 "Prep an SD card, flash Raspberry Pi OS, stage "
                 "RetroArch")
    uninstaller = base / "uninstall.sh"
    uninstaller.write_text(
        "#!/bin/sh\n"
        "cd /tmp\n"
        'rm -f "$HOME/.local/bin/raspberry-ark"\n'
        'rm -f "$HOME/.local/share/applications/raspberry-ark.desktop"\n'
        'rm -rf "$HOME/.local/share/raspberry-ark"\n'
        "echo 'The Raspberry Ark removed.'\n", encoding="utf-8")
    make_executable(uninstaller)
    return "Run it from your applications menu, or type: raspberry-ark"


# -------------------------------------------------------- desktop: macOS
def install_macos(home, base):
    written = write_payload(base, [DESKTOP_FILE, PI_FILE,
                                   "assets/emblem.png"])
    app = written[DESKTOP_FILE]
    make_executable(app)
    make_executable(written[PI_FILE])
    launcher = base / "The Raspberry Ark.command"
    launcher.write_text(
        "#!/bin/sh\n"
        'python3 "' + str(app) + '"\n'
        "echo\n"
        "echo 'Press any key to close.'\n"
        "read -n 1 -s\n", encoding="utf-8")
    make_executable(launcher)
    desk = home / "Desktop" / "The Raspberry Ark.command"
    try:
        shutil.copyfile(launcher, desk)
        make_executable(desk)
    except OSError:
        pass
    uninstaller = base / "Uninstall The Raspberry Ark.command"
    uninstaller.write_text(
        "#!/bin/sh\n"
        "cd /tmp\n"
        'rm -f "$HOME/Desktop/The Raspberry Ark.command"\n'
        'rm -rf "$HOME/Applications/The-Raspberry-Ark"\n'
        "echo 'The Raspberry Ark removed.'\n", encoding="utf-8")
    make_executable(uninstaller)
    return 'Double-click "The Raspberry Ark" on the Desktop.'


# ------------------------------------------------------ desktop: Windows
def install_windows(home, base):
    written = write_payload(base, [DESKTOP_FILE, PI_FILE,
                                   "assets/emblem.png"])
    make_executable(written[PI_FILE])
    pycmd = "py -3" if shutil.which("py") else "python"
    run_bat = base / "run.bat"
    run_bat.write_text("@echo off\n" + pycmd + ' "%~dp0'
                       + DESKTOP_FILE + '" %*\n', encoding="utf-8")
    desktop_link = home / "Desktop" / "The Raspberry Ark.lnk"
    startmenu = (Path(os.environ.get("APPDATA",
                                     home / "AppData" / "Roaming"))
                 / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    startmenu.mkdir(parents=True, exist_ok=True)
    start_link = startmenu / "The Raspberry Ark.lnk"
    linked = False
    for link in (desktop_link, start_link):
        try:
            ps = ("$s=(New-Object -ComObject WScript.Shell)"
                  ".CreateShortcut('" + str(link)
                  + "');$s.TargetPath='" + str(run_bat)
                  + "';$s.WorkingDirectory='" + str(base)
                  + "';$s.Save()")
            subprocess.run(["powershell", "-NoProfile",
                            "-ExecutionPolicy", "Bypass", "-Command",
                            ps], check=True, capture_output=True,
                           timeout=60)
            linked = True
        except Exception:
            pass
    if not linked:
        (home / "Desktop" / "The Raspberry Ark.bat").write_text(
            '@echo off\ncall "' + str(run_bat) + '"\npause\n',
            encoding="utf-8")
    uninstall_bat = base / "uninstall.bat"
    uninstall_bat.write_text(
        "@echo off\n"
        "cd /d %TEMP%\n"
        'del "%USERPROFILE%\\Desktop\\The Raspberry Ark.lnk" 2>nul\n'
        'del "%USERPROFILE%\\Desktop\\The Raspberry Ark.bat" 2>nul\n'
        'del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\'
        'The Raspberry Ark.lnk" 2>nul\n'
        'reg delete "HKCU\\Software\\Microsoft\\Windows\\'
        'CurrentVersion\\Uninstall\\TheRaspberryArk" /f 2>nul\n'
        'rmdir /s /q "%LOCALAPPDATA%\\The-Raspberry-Ark"\n'
        "echo The Raspberry Ark removed.\n"
        "pause\n", encoding="utf-8")
    try:
        import winreg
        key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"
            "TheRaspberryArk")
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ,
                          APP_NAME + " " + APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ,
                          PUBLISHER)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ,
                          str(base))
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ,
                          '"' + str(uninstall_bat) + '"')
        winreg.CloseKey(key)
    except Exception:
        pass
    return ('Double-click "The Raspberry Ark" on the Desktop or in '
            "the Start Menu.")


# -------------------------------------------------------------- uninstall
def uninstall(os_id):
    home, base = locations(os_id)
    names = ("raspberry-ark", "raspberry-ark-pi")
    if os_id == "windows":
        for p in (home / "Desktop" / "The Raspberry Ark.lnk",
                  home / "Desktop" / "The Raspberry Ark.bat",
                  Path(os.environ.get("APPDATA",
                                      home / "AppData" / "Roaming"))
                  / "Microsoft" / "Windows" / "Start Menu" / "Programs"
                  / "The Raspberry Ark.lnk"):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            import winreg
            winreg.DeleteKey(
                winreg.HKEY_CURRENT_USER,
                "Software\\Microsoft\\Windows\\CurrentVersion\\"
                "Uninstall\\TheRaspberryArk")
        except Exception:
            pass
    elif os_id == "macos":
        try:
            (home / "Desktop" / "The Raspberry Ark.command").unlink()
        except OSError:
            pass
    else:
        for cmd in names:
            for p in (home / ".local" / "bin" / cmd,
                      home / ".local" / "share" / "applications"
                      / (cmd + ".desktop")):
                try:
                    p.unlink()
                except OSError:
                    pass
    shutil.rmtree(base, ignore_errors=True)
    print(APP_NAME + " removed from " + str(base))


def main():
    if sys.version_info < (3, 9):
        print("Python 3.9 or newer is required.")
        return 1
    os_id = detect_os()
    if "--uninstall" in sys.argv:
        uninstall(os_id)
        return 0
    home, base = locations(os_id)
    print("=" * 64)
    print(APP_NAME + " " + APP_VERSION + " - universal installer")
    if os_id == "linux" and detect_pi():
        print("Detected: Raspberry Pi running Raspberry Pi OS - "
              "installing the Pi half (RetroArch installer).")
        print("Install folder: " + str(base))
        print("=" * 64)
        return install_pi(home, base)
    print("Detected operating system: " + os_label(os_id)
          + " - installing the desktop half (SD prep + flash + "
            "staging).")
    print("Install folder: " + str(base))
    print("=" * 64)
    if os_id == "windows":
        how = install_windows(home, base)
    elif os_id == "macos":
        how = install_macos(home, base)
    else:
        how = install_linux(home, base)
    try:
        shutil.copyfile(Path(__file__).resolve(),
                        base / "Raspberry-Ark-Setup.py")
    except OSError:
        pass
    print()
    print("Installed. " + how)
    print(SD_NOTE)
    print("Uninstall any time with the uninstaller in the install "
          "folder, or run this Setup again with --uninstall.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            z.write(HERE / name, name)
    payload = base64.b64encode(
        zlib.compress(buf.getvalue(), 9)).decode("ascii")
    chunks = [payload[i:i + 76] for i in range(0, len(payload), 76)]
    payload_block = "(\n" + "\n".join(f'    "{c}"' for c in chunks) + "\n)"
    setup_src = TEMPLATE.replace('PAYLOAD_B64 = "@@PAYLOAD@@"',
                                 "PAYLOAD_B64 = " + payload_block)
    compile(setup_src, str(OUT), "exec")  # syntax check before writing
    OUT.write_text(setup_src, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes); "
          f"payload zip is {len(buf.getvalue()):,} bytes.")


if __name__ == "__main__":
    main()
