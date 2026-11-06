#!/usr/bin/env python3
"""
The Raspberry Ark (Pi side) — RetroArch installer + setup for a
Raspberry Pi running Raspberry Pi OS (v1.0.0, by Delukz).

This is half of "The Raspberry Ark". The desktop half prepares an SD
card, flashes Raspberry Pi OS and stages this file on the card's boot
partition with a first-boot hook, so a fresh card sets itself up. You
can also copy this file to a Pi and run it directly:

  1. Detect your exact Raspberry Pi model (device tree) and your
     Raspberry Pi OS version (/etc/os-release).
  2. Check compatibility and tell you plainly what your Pi can run.
  3. Install RetroArch plus the right libretro cores for your model
     from the official Raspberry Pi OS / Debian repositories (apt).
     SNES (snes9x) is in every tier; PlayStation (pcsx-rearmed) is in
     tiers A and B (Pi 3 and up).
  4. Write a tuned RetroArch config, including netplay settings
     (port 55435, optional relay server).
  5. Set the Pi to auto-boot straight into RetroArch on startup
     (console autologin — no desktop — plus a terminal launcher
     block in ~/.bash_profile).
  6. Create a Games Library folder skeleton and explain where games
     can be obtained legally (homebrew / public-domain ROMs and your
     own legally-owned backups).

No games or BIOS files are included or downloaded.

Usage:
  raspberry_ark_pi.py              interactive menu
  raspberry_ark_pi.py detect       show model / OS / compatibility
  raspberry_ark_pi.py install      full RetroArch install (+ autoboot)
  raspberry_ark_pi.py config       (re)write the RetroArch config only
  raspberry_ark_pi.py netplay [relay-host]   (re)write netplay settings
  raspberry_ark_pi.py autoboot     set up auto-boot into RetroArch
  raspberry_ark_pi.py library      show the Games Library guidance
  raspberry_ark_pi.py uninstall    remove Ark config + library folders
  raspberry_ark_pi.py --dry-run install   print every step, change nothing

Test hooks (used by the smoke tests, harmless in normal use):
  ARK_MODEL_FILE, ARK_CPUINFO_FILE, ARK_OS_RELEASE_FILE and
  ARK_RPI_ISSUE_FILE override the system files detection reads.
"""

import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP_NAME = "The Raspberry Ark"
APP_VERSION = "1.0.0"
DRY_RUN = "--dry-run" in sys.argv

# ------------------------------------------------------------------ paths
MODEL_FILE = os.environ.get("ARK_MODEL_FILE", "/proc/device-tree/model")
CPUINFO_FILE = os.environ.get("ARK_CPUINFO_FILE", "/proc/cpuinfo")
OS_RELEASE_FILE = os.environ.get("ARK_OS_RELEASE_FILE", "/etc/os-release")
RPI_ISSUE_FILE = os.environ.get("ARK_RPI_ISSUE_FILE", "/etc/rpi-issue")

HOME = Path.home()
CONFIG_DIR = HOME / ".config" / "retroarch"
CONFIG_FILE = CONFIG_DIR / "retroarch.cfg"
ARK_HOME = HOME / "RaspberryArk"
ROMS_DIR = ARK_HOME / "roms"


# ------------------------------------------------------------- detection
# Revision-code table (subset of the well-known codes) — the device-tree
# model string is the primary source; this is a fallback / cross-check.
REVISION_MODELS = {
    "a03111": "Raspberry Pi 4 Model B", "b03111": "Raspberry Pi 4 Model B",
    "b03112": "Raspberry Pi 4 Model B", "b03114": "Raspberry Pi 4 Model B",
    "b03115": "Raspberry Pi 4 Model B", "c03111": "Raspberry Pi 4 Model B",
    "c03112": "Raspberry Pi 4 Model B", "c03114": "Raspberry Pi 4 Model B",
    "c03115": "Raspberry Pi 4 Model B", "d03114": "Raspberry Pi 4 Model B",
    "d03115": "Raspberry Pi 4 Model B", "c03130": "Raspberry Pi 400",
    "a03140": "Raspberry Pi CM4", "b03140": "Raspberry Pi CM4",
    "c03140": "Raspberry Pi CM4", "d03140": "Raspberry Pi CM4",
    "b04170": "Raspberry Pi 5", "c04170": "Raspberry Pi 5",
    "d04170": "Raspberry Pi 5",
    "a02082": "Raspberry Pi 3 Model B", "a22082": "Raspberry Pi 3 Model B",
    "a32082": "Raspberry Pi 3 Model B", "a020d3": "Raspberry Pi 3 Model B+",
    "9020e1": "Raspberry Pi 3 Model A+",
    "a01041": "Raspberry Pi 2 Model B", "a21041": "Raspberry Pi 2 Model B",
    "a22042": "Raspberry Pi 2 Model B",
    "900092": "Raspberry Pi Zero", "900093": "Raspberry Pi Zero",
    "9000c1": "Raspberry Pi Zero W", "902120": "Raspberry Pi Zero 2 W",
}


def _read(path):
    try:
        return Path(path).read_text(errors="replace").replace("\x00", "")
    except OSError:
        return ""


def detect_model():
    """Return (model_name, tier) — tier A best .. D weakest, None if no Pi."""
    model = _read(MODEL_FILE).strip()
    revision = ""
    for line in _read(CPUINFO_FILE).splitlines():
        if line.lower().startswith("revision"):
            revision = line.split(":")[-1].strip().lower()[-6:]
    if not model and revision in REVISION_MODELS:
        model = REVISION_MODELS[revision]
    if revision in REVISION_MODELS and not model:
        model = REVISION_MODELS[revision]
    if not model:
        return None, None
    m = model.lower()
    if "raspberry pi 5" in m:
        tier = "A"
    elif ("raspberry pi 4" in m or "pi 400" in m or "compute module 4" in m
          or "cm4" in m):
        tier = "A"
    elif "zero 2" in m or "raspberry pi 3" in m:
        tier = "B"
    elif "raspberry pi 2" in m:
        tier = "C"
    elif "zero" in m or "raspberry pi" in m:
        tier = "D"
    else:
        return model, None
    return model, tier


def detect_os():
    """Return dict with pretty name, codename, is_pi_os, arch, support."""
    info = {}
    for line in _read(OS_RELEASE_FILE).splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip().strip('"')
    codename = info.get("VERSION_CODENAME", "").lower()
    is_pi_os = Path(RPI_ISSUE_FILE).exists() or \
        "raspberry" in info.get("PRETTY_NAME", "").lower() or \
        "raspbian" in info.get("PRETTY_NAME", "").lower() or \
        info.get("ID", "").lower() == "raspbian"
    arch = platform.machine()
    try:
        out = subprocess.run(["dpkg", "--print-architecture"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            arch = out.stdout.strip()
    except Exception:
        pass
    if codename in ("trixie", "bookworm"):
        support = "full"
    elif codename == "bullseye":
        support = "supported"
    elif codename == "buster":
        support = "legacy"
    elif codename:
        support = "old"
    else:
        support = "unknown"
    return {
        "pretty": info.get("PRETTY_NAME", "Unknown OS"),
        "codename": codename or "unknown",
        "is_pi_os": is_pi_os,
        "arch": arch,
        "support": support,
    }


TIER_NOTES = {
    "A": "Top tier — PS1 and N64 included, everything below flies.",
    "B": "Strong — PS1 (PCSX-ReARMed) and all 8/16-bit included.",
    "C": "Basic — 8/16-bit cores included; PS1/N64 would crawl.",
    "D": "Minimal — the lightest cores (SNES included); expect slowdowns.",
}
OS_NOTES = {
    "full": "Current Raspberry Pi OS — fully supported.",
    "supported": "Raspberry Pi OS Bullseye — supported.",
    "legacy": "Raspberry Pi OS Buster (legacy) — packages may be archived; "
              "upgrade to Bookworm/Trixie is recommended.",
    "old": "Very old OS release — apt may no longer serve packages.",
    "unknown": "Could not identify the OS release.",
}


def compatibility(model, tier, osinfo, force=False):
    """Return (ok: bool, messages: list[str])."""
    msgs = []
    if model is None or tier is None:
        msgs.append("✗ No Raspberry Pi detected — Ark installs RetroArch "
                    "on a Pi running Raspberry Pi OS.")
        return (force, msgs + (["--force given: continuing anyway."]
                               if force else []))
    msgs.append(f"✓ Detected: {model} (tier {tier}) — {TIER_NOTES[tier]}")
    msgs.append(f"✓ OS: {osinfo['pretty']} [{osinfo['codename']}], "
                f"architecture {osinfo['arch']} — {OS_NOTES[osinfo['support']]}")
    if not osinfo["is_pi_os"]:
        msgs.append("⚠ This doesn't look like Raspberry Pi OS — apt "
                    "packages may differ.")
    if osinfo["support"] in ("legacy", "old"):
        msgs.append("⚠ Old OS — install may partially fail; results vary.")
    return True, msgs


# -------------------------------------------------------------- progress
def progress(pct, label):
    pct = max(0, min(100, int(pct)))
    filled = int(pct / 5)
    bar = "█" * filled + "░" * (20 - filled)
    print(f"\r[{bar}] {pct:3d}%  {label:<58}", end="", flush=True)
    if pct >= 100:
        print()


def run(cmd, sudo=False):
    full = (["sudo"] if sudo else []) + cmd
    print(("  [dry-run] " if DRY_RUN else "  $ ") + " ".join(full))
    if DRY_RUN:
        return 0
    return subprocess.run(full).returncode


def apt_available(pkg):
    if DRY_RUN:
        return True
    try:
        out = subprocess.run(["apt-cache", "show", pkg],
                             capture_output=True, timeout=20)
        return out.returncode == 0
    except Exception:
        return False


# -------------------------------------------------------------- packages
BASE_TOOLS = ["ca-certificates"]
RETROARCH_PKGS = ["retroarch"]
OPTIONAL_PKGS = ["retroarch-assets", "libretro-core-info"]
BASE_CORES = [
    "libretro-gambatte",       # Game Boy / Color
    "libretro-nestopia",       # NES
    "libretro-snes9x",         # SNES
    "libretro-mgba",           # GBA / GB
    "libretro-genesisplusgx",  # Genesis / Master System / Game Gear
    "libretro-stella",         # Atari 2600
    "libretro-prosystem",      # Atari 7800
]
TIER_B_CORES = [
    "libretro-pcsx-rearmed",   # PlayStation 1 (fast on ARM)
    "libretro-beetle-pce-fast",  # PC Engine / TurboGrafx-16
]
TIER_A_CORES = [
    "libretro-mupen64plus",    # Nintendo 64
]
GROUP_LIST = ["video", "input", "audio", "render"]


def core_set(tier):
    cores = list(BASE_CORES)
    if tier in ("A", "B"):
        cores += TIER_B_CORES
    if tier == "A":
        cores += TIER_A_CORES
    if tier == "D":
        # Lightest set — but snes9x stays: SNES is in every tier.
        cores = ["libretro-gambatte", "libretro-nestopia",
                 "libretro-snes9x", "libretro-stella"]
    return cores


# ---------------------------------------------------------------- config
def multiarch_triplet(arch):
    return {"aarch64": "aarch64-linux-gnu", "arm64": "aarch64-linux-gnu",
            "armv7l": "arm-linux-gnueabihf",
            "armv6l": "arm-linux-gnueabihf",
            "armhf": "arm-linux-gnueabihf"}.get(arch, "aarch64-linux-gnu")


def build_config(tier, osinfo):
    triplet = multiarch_triplet(osinfo["arch"])
    video = "vulkan" if (tier == "A" and "raspberry pi 5"
                         in (detect_model()[0] or "").lower()) else "gl"
    if osinfo["arch"] in ("aarch64", "arm64"):
        updater = "https://buildbot.libretro.com/nightly/linux/aarch64/latest/"
    else:
        updater = ("https://buildbot.libretro.com/nightly/linux/"
                   "armv7-neon-hf/latest/")
    lines = {
        # Netplay (RetroArch built-in): host or join on port 55435.
        # netplay_use_mitm_server turns on the free public relay
        # ("MITM server") lobby; netplay_mitm_server can pin a
        # specific relay host if you run or prefer one.
        "netplay_ip_port": "55435",
        "netplay_nickname": "ArkPlayer",
        "netplay_use_mitm_server": "false",
        "netplay_mitm_server": "",
        "netplay_delay_frames": "2",
        "video_driver": video,
        "audio_driver": "alsathread",
        "input_driver": "udev",
        "menu_driver": "ozone",
        "libretro_directory": f"/usr/lib/{triplet}/libretro",
        "libretro_info_path": "/usr/share/libretro/info",
        "assets_directory": "/usr/share/retroarch/assets",
        "core_updater_buildbot_url": updater,
        "core_updater_buildbot_assets_url":
            "https://buildbot.libretro.com/assets/",
        "savefile_directory": str(ARK_HOME / "saves"),
        "savestate_directory": str(ARK_HOME / "states"),
        "system_directory": str(ARK_HOME / "system"),
        "rgui_browser_directory": str(ROMS_DIR),
        "video_threaded": "true",
        "menu_show_online_updater": "true",
        "menu_show_core_updater": "true",
    }
    out = ["# RetroArch configuration written by The Raspberry Ark "
           f"v{APP_VERSION}"]
    out += [f'{k} = "{v}"' for k, v in sorted(lines.items())]
    return "\n".join(out) + "\n"


ROM_SYSTEMS = ["nes", "snes", "gb", "gbc", "gba", "genesis", "segacd",
               "psx", "n64", "atari2600", "atari7800", "pcengine",
               "mastersystem", "gamegear"]


def write_config(tier, osinfo):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists() and not DRY_RUN:
        backup = CONFIG_FILE.with_suffix(".cfg.bak")
        shutil.copyfile(CONFIG_FILE, backup)
        print(f"  Existing config backed up to {backup}")
    if DRY_RUN:
        print(f"  [dry-run] would write {CONFIG_FILE}:")
        print(build_config(tier, osinfo))
        return
    CONFIG_FILE.write_text(build_config(tier, osinfo), encoding="utf-8")
    print(f"  Config written: {CONFIG_FILE}")
    for sub in ("saves", "states", "system"):
        (ARK_HOME / sub).mkdir(parents=True, exist_ok=True)
    for system in ROM_SYSTEMS:
        (ROMS_DIR / system).mkdir(parents=True, exist_ok=True)
    note = ROMS_DIR / "README.txt"
    if not note.exists():
        note.write_text(LIBRARY_README, encoding="utf-8")
    print(f"  ROMs folder ready: {ROMS_DIR}")




# ------------------------------------------------------------ games library
LIBRARY_README = """The Raspberry Ark — Games Library
================================

Put game files in the folder for their system (nes, snes, gb, gbc,
gba, genesis, segacd, psx, n64, atari2600, atari7800, pcengine,
mastersystem, gamegear). Saves live in ../saves, save states in
../states, and BIOS files (your own, e.g. for PlayStation) in
../system.

The Raspberry Ark includes NO games and NO BIOS files. Legal ways
to fill this library:

  * Homebrew and public-domain ROMs — games released for free by
    their creators:
      - Homebrew Hub (homebrew database for classic consoles)
      - PDRoms (public-domain and freeware ROM archive)
      - itch.io homebrew (search "homebrew" for NES / Game Boy /
        Genesis games sold or given away by their developers)
  * Your own legally-owned backups — dump cartridges/discs you own
    with a cartridge reader or a disc drive, and copy the files
    here. In most places making a personal backup of media you own
    is the legal route; downloading commercial ROMs you do not own
    is not, and this app does not download games for you.
"""


def cmd_library():
    print(LIBRARY_README)
    print(f"Library folder: {ROMS_DIR}")
    return 0


# --------------------------------------------------------------- autoboot
# Legacy desktop autostart entry written by earlier versions; kept
# only so setup/uninstall can remove it (console boot replaced it).
AUTOSTART_DIR = HOME / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "retroarch.desktop"
PROFILE_FILE = HOME / ".bash_profile"
ARK_BLOCK_START = "# >>> The Raspberry Ark - RetroArch auto-start >>>"
ARK_BLOCK_END = "# <<< The Raspberry Ark - RetroArch auto-start <<<"
ARK_PROFILE_BLOCK = (
    ARK_BLOCK_START + "\n"
    "# Boot-to-terminal auto-start: on the first console (tty1) only,\n"
    "# launch RetroArch fullscreen. Quitting RetroArch lands back at\n"
    "# the terminal prompt. Remove with: raspberry-ark-pi uninstall\n"
    'if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then\n'
    "    retroarch --fullscreen\n"
    "fi\n"
    + ARK_BLOCK_END + "\n")


def _strip_profile_block(text):
    """Remove the Ark auto-start block from .bash_profile text."""
    out, skipping = [], False
    for line in text.splitlines(keepends=True):
        if line.strip() == ARK_BLOCK_START:
            skipping = True
            continue
        if line.strip() == ARK_BLOCK_END:
            skipping = False
            continue
        if not skipping:
            out.append(line)
    return "".join(out)


def setup_autoboot():
    """Auto-boot straight into RetroArch — via the terminal, no desktop.

    Method (Delukz's spec):
      1. raspi-config nonint do_boot_behaviour B2 — boot to the
         console with autologin. The desktop is never started.
      2. A marker-delimited block in ~/.bash_profile launches
         `retroarch --fullscreen` when the autologin shell lands on
         tty1. RetroArch's gl/vulkan drivers run directly on
         KMS/DRM from the console (the same way RetroPie launches),
         so no X/Wayland session is needed. Quitting RetroArch
         drops back to the terminal prompt.
    Any legacy desktop autostart entry from an earlier version is
    removed, so the two launchers can never double-fire.
    """
    print("  Auto-boot setup: boot to terminal (console autologin) + "
          "RetroArch launch from ~/.bash_profile.")
    if DRY_RUN:
        print("  [dry-run] would run: sudo raspi-config nonint "
              "do_boot_behaviour B2")
        print(f"  [dry-run] would ensure {PROFILE_FILE} contains:")
        for line in ARK_PROFILE_BLOCK.splitlines():
            print(f"    {line}")
        print(f"  [dry-run] would remove legacy {AUTOSTART_FILE} "
              "if present")
        return
    if shutil.which("raspi-config"):
        rc = run(["raspi-config", "nonint", "do_boot_behaviour", "B2"],
                 sudo=True)
        if rc != 0:
            print("  raspi-config returned an error — set boot "
                  "behaviour manually: sudo raspi-config -> "
                  "System Options -> Boot / Auto Login -> Console "
                  "Autologin.")
    else:
        print("  raspi-config not found — set Console Autologin "
              "manually with raspi-config, or the ~/.bash_profile "
              "block below still launches RetroArch whenever you "
              "log in on tty1.")
    if AUTOSTART_FILE.exists():
        AUTOSTART_FILE.unlink()
        print(f"  Removed legacy desktop autostart entry: "
              f"{AUTOSTART_FILE}")
    existing = PROFILE_FILE.read_text(encoding="utf-8") \
        if PROFILE_FILE.exists() else ""
    stripped = _strip_profile_block(existing)
    if stripped and not stripped.endswith("\n"):
        stripped += "\n"
    PROFILE_FILE.write_text(stripped + ARK_PROFILE_BLOCK,
                            encoding="utf-8")
    print(f"  Terminal launcher written: {PROFILE_FILE}")


def cmd_netplay(relay=""):
    """(Re)write the config, optionally pinning a netplay relay host."""
    model, tier = detect_model()
    osinfo = detect_os()
    write_config(tier or "B", osinfo)
    if relay:
        text = CONFIG_FILE.read_text(encoding="utf-8") \
            if CONFIG_FILE.exists() else ""
        out = []
        for line in text.splitlines():
            if line.startswith("netplay_use_mitm_server"):
                line = 'netplay_use_mitm_server = "true"'
            elif line.startswith("netplay_mitm_server"):
                line = f'netplay_mitm_server = "{relay}"'
            out.append(line)
        if not DRY_RUN:
            CONFIG_FILE.write_text("\n".join(out) + "\n",
                                   encoding="utf-8")
        print(f"  Netplay relay pinned to: {relay}")
    print("  Netplay: RetroArch menu -> Netplay -> host a game or "
          "join by IP. Port 55435.")
    print("  For internet play without port-forwarding, enable the "
          "relay (MITM) server in RetroArch's netplay settings — it "
          "uses RetroArch's free public lobby/relay service.")
    return 0


# --------------------------------------------------------------- install
def cmd_detect(force=False):
    model, tier = detect_model()
    osinfo = detect_os()
    ok, msgs = compatibility(model, tier, osinfo, force)
    for m in msgs:
        print(m)
    return ok


def cmd_install(force=False):
    model, tier = detect_model()
    osinfo = detect_os()
    ok, msgs = compatibility(model, tier, osinfo, force)
    print("=" * 64)
    print(f"{APP_NAME} v{APP_VERSION} — RetroArch installer")
    for m in msgs:
        print(m)
    print("=" * 64)
    if not ok:
        print("Not compatible — nothing installed. (Use --force to "
              "override.)")
        return 1
    if os.geteuid() != 0 and not shutil.which("sudo") and not DRY_RUN:
        print("sudo is required to install packages. Install sudo or run "
              "as root.")
        return 1

    progress(5, "Updating package lists…")
    run(["apt-get", "update"], sudo=True)

    progress(15, "Installing base tools…")
    run(["apt-get", "install", "-y"] + BASE_TOOLS, sudo=True)

    progress(30, "Installing RetroArch…")
    run(["apt-get", "install", "-y"] + RETROARCH_PKGS, sudo=True)

    progress(45, "Installing configuration packages…")
    skipped = []
    for pkg in OPTIONAL_PKGS:
        if apt_available(pkg):
            run(["apt-get", "install", "-y", pkg], sudo=True)
        else:
            skipped.append(pkg)

    cores = core_set(tier)
    step = 25 / max(1, len(cores))
    pct = 55.0
    for i, pkg in enumerate(cores):
        pct = 55 + step * (i + 1)
        if apt_available(pkg):
            run(["apt-get", "install", "-y", pkg], sudo=True)
        else:
            skipped.append(pkg)
        progress(int(pct), f"Core {i + 1}/{len(cores)}: {pkg}")

    progress(85, "Adding your user to video/input/audio groups…")
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if user:
        run(["usermod", "-aG", ",".join(GROUP_LIST), user], sudo=True)

    progress(88, "Writing RetroArch configuration…")
    write_config(tier, osinfo)

    if "--no-autoboot" not in sys.argv:
        progress(92, "Setting up auto-boot into RetroArch…")
        setup_autoboot()

    progress(97, "Verifying the install…")
    version = ""
    if not DRY_RUN and shutil.which("retroarch"):
        out = subprocess.run(["retroarch", "--version"],
                             capture_output=True, text=True, timeout=20)
        version = (out.stdout or out.stderr).strip().splitlines()[0] \
            if (out.stdout or out.stderr) else ""
    progress(100, "Done.")
    print()
    print("=" * 64)
    print(f"RetroArch installed for {model} on {osinfo['pretty']}.")
    if version:
        print(f"  {version}")
    if skipped:
        print("  Not available in this OS release (skipped): "
              + ", ".join(skipped))
        print("  You can fetch extra cores inside RetroArch: "
              "Online Updater → Core Downloader.")
    print(f"  Config: {CONFIG_FILE}")
    print(f"  ROMs:   {ROMS_DIR}  (add your own game backups)")
    print("  Reboot and the Pi starts straight into RetroArch "
          "(auto-boot). Log out and back in once so the group "
          "changes apply.")
    print("=" * 64)
    return 0


def cmd_uninstall():
    removed = []
    if PROFILE_FILE.exists():
        text = PROFILE_FILE.read_text(encoding="utf-8")
        stripped = _strip_profile_block(text)
        if stripped != text:
            PROFILE_FILE.write_text(stripped, encoding="utf-8")
            removed.append(f"{PROFILE_FILE} (auto-start block)")
    if AUTOSTART_FILE.exists():
        AUTOSTART_FILE.unlink()
        removed.append(str(AUTOSTART_FILE))
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        removed.append(str(CONFIG_FILE))
    if ARK_HOME.exists():
        shutil.rmtree(ARK_HOME, ignore_errors=True)
        removed.append(str(ARK_HOME))
    print("Removed: " + (", ".join(removed) if removed else "nothing"))
    print("To remove the RetroArch packages themselves:")
    print("  sudo apt-get purge retroarch 'libretro-*'")
    return 0


def menu():
    print("=" * 64)
    print(f"{APP_NAME} v{APP_VERSION} — RetroArch for your Raspberry Pi")
    print("=" * 64)
    cmd_detect()
    print()
    print("  1) Install RetroArch + cores + config + auto-boot")
    print("  2) Rewrite the RetroArch config only")
    print("  3) Set up auto-boot into RetroArch")
    print("  4) Netplay setup (rewrite netplay config)")
    print("  5) Games Library — where to get games legally")
    print("  6) Uninstall (Ark config + library folders)")
    print("  7) Quit")
    try:
        choice = input("Choose [1-7]: ").strip()
    except EOFError:
        choice = "7"
    if choice == "1":
        return cmd_install()
    if choice == "2":
        model, tier = detect_model()
        osinfo = detect_os()
        write_config(tier or "B", osinfo)
        return 0
    if choice == "3":
        setup_autoboot()
        return 0
    if choice == "4":
        return cmd_netplay()
    if choice == "5":
        return cmd_library()
    if choice == "6":
        return cmd_uninstall()
    return 0


def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    cmd = args[0] if args else ""
    if cmd == "detect":
        return 0 if cmd_detect(force) else 2
    if cmd == "install":
        return cmd_install(force)
    if cmd == "config":
        model, tier = detect_model()
        osinfo = detect_os()
        write_config(tier or "B", osinfo)
        return 0
    if cmd == "netplay":
        return cmd_netplay(args[1] if len(args) > 1 else "")
    if cmd == "autoboot":
        setup_autoboot()
        return 0
    if cmd == "library":
        return cmd_library()
    if cmd == "uninstall":
        return cmd_uninstall()
    return menu()


if __name__ == "__main__":
    sys.exit(main())
