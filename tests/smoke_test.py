#!/usr/bin/env python3
"""
Smoke tests for The Raspberry Ark — no Raspberry Pi required.

Pi-side detection runs off fixture files (tests/fixtures/) through
the ARK_* environment overrides, installs run with --dry-run, and
the desktop staging step runs against a fake boot partition in a
temp folder. Nothing on the machine changes.

Run:  python3 tests/smoke_test.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PI_APP = ROOT / "raspberry_ark_pi.py"
DESKTOP_APP = ROOT / "raspberry_ark.py"
FIX = HERE / "fixtures"

FAILURES = []


def run_pi(args, model, osrel, rpi_issue=True, home=None):
    env = dict(os.environ)
    env["ARK_MODEL_FILE"] = str(FIX / model)
    env["ARK_OS_RELEASE_FILE"] = str(FIX / osrel)
    env["ARK_CPUINFO_FILE"] = str(FIX / "model_none.txt")
    env["ARK_RPI_ISSUE_FILE"] = str(FIX / "rpi_issue.txt") if rpi_issue \
        else str(FIX / "no_such_file.txt")
    if home:
        env["HOME"] = str(home)
    return subprocess.run([sys.executable, str(PI_APP)] + args,
                          capture_output=True, text=True, env=env,
                          timeout=60)


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else
                                                  f" — {detail}"))
    if not cond:
        FAILURES.append(name)


def detect_case(name, model, osrel, want_text, want_rc, rpi_issue=True):
    r = run_pi(["detect"], model, osrel, rpi_issue)
    check(name, r.returncode == want_rc and want_text in r.stdout,
          f"rc={r.returncode} out={r.stdout.strip()[:160]}")


def main():
    # ------------------------------------------------ Pi detection
    detect_case("Pi 5 + Trixie -> tier A", "model_pi5.txt",
                "os_trixie.txt",
                "Raspberry Pi 5 Model B Rev 1.1 (tier A)", 0)
    detect_case("Pi 4 + Bookworm -> tier A", "model_pi4.txt",
                "os_bookworm.txt", "(tier A)", 0)
    detect_case("Pi 3 + Bullseye -> tier B", "model_pi3.txt",
                "os_bullseye.txt", "(tier B)", 0)
    detect_case("Pi 2 + Bookworm -> tier C", "model_pi2.txt",
                "os_bookworm.txt", "(tier C)", 0)
    detect_case("Pi Zero W + Buster -> tier D + legacy warning",
                "model_pizero.txt", "os_buster.txt", "(tier D)", 0)
    r = run_pi(["detect"], "model_pizero.txt", "os_buster.txt")
    check("Buster shows legacy note", "legacy" in r.stdout.lower(),
          r.stdout.strip()[:160])
    detect_case("Not a Pi -> incompatible", "model_none.txt",
                "os_debian.txt", "No Raspberry Pi detected", 2,
                rpi_issue=False)

    # --------------------------------------- Pi dry-run install plan
    with tempfile.TemporaryDirectory() as tmp:
        r = run_pi(["--dry-run", "install"], "model_pi5.txt",
                   "os_trixie.txt", home=tmp)
        out = r.stdout
        check("Dry-run install rc=0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr.strip()[:200]}")
        check("Plans apt retroarch",
              "apt-get install -y retroarch" in out, out[:200])
        check("Tier A plans N64 core", "libretro-mupen64plus" in out)
        check("Tier A plans PS1 core (pcsx-rearmed)",
              "libretro-pcsx-rearmed" in out)
        check("Tier A plans SNES core (snes9x)",
              "libretro-snes9x" in out)
        check("Config uses vulkan on Pi 5",
              'video_driver = "vulkan"' in out, out[-400:])
        check("Config carries netplay port 55435",
              'netplay_ip_port = "55435"' in out, out[-400:])
        check("Config carries netplay relay field",
              "netplay_mitm_server" in out, out[-400:])
        check("Install plans auto-boot setup",
              "do_boot_behaviour B2" in out
              and ".bash_profile" in out
              and "tty1" in out, out[-600:])
        egg = "saucy" + " pickle"
        check("No easter egg in the plan", egg not in out)

    with tempfile.TemporaryDirectory() as tmp:
        r = run_pi(["--dry-run", "install"], "model_pi3.txt",
                   "os_bullseye.txt", home=tmp)
        out = r.stdout
        check("Tier B plans PS1 core", "libretro-pcsx-rearmed" in out)
        check("Tier B plans SNES core", "libretro-snes9x" in out)
        check("Tier B has no N64 core",
              "libretro-mupen64plus" not in out)

    with tempfile.TemporaryDirectory() as tmp:
        r = run_pi(["--dry-run", "install"], "model_pi2.txt",
                   "os_bookworm.txt", home=tmp)
        out = r.stdout
        check("Tier C plans SNES core", "libretro-snes9x" in out)
        check("Tier C has no PS1 core",
              "libretro-pcsx-rearmed" not in out)

    with tempfile.TemporaryDirectory() as tmp:
        r = run_pi(["--dry-run", "install"], "model_pizero.txt",
                   "os_buster.txt", home=tmp)
        out = r.stdout
        check("Tier D still plans SNES core (snes9x in every tier)",
              "libretro-snes9x" in out)
        check("Tier D has no PS1 core",
              "libretro-pcsx-rearmed" not in out)

    r = run_pi(["--dry-run", "install"], "model_none.txt",
               "os_debian.txt", rpi_issue=False)
    check("Dry-run install refuses a non-Pi",
          r.returncode == 1 and "Not compatible" in r.stdout,
          f"rc={r.returncode}")

    r = run_pi(["library"], "model_pi5.txt", "os_trixie.txt")
    check("Library guidance names legal sources only",
          r.returncode == 0 and "Homebrew Hub" in r.stdout
          and "legally-owned backups" in r.stdout,
          r.stdout[:160])

    # --------------------------------- desktop staging (fake boot)
    with tempfile.TemporaryDirectory() as tmp:
        boot = Path(tmp)
        (boot / "cmdline.txt").write_text(
            "console=tty1 root=PARTUUID=x-02 rootfstype=ext4 "
            "rootwait quiet\n")
        (boot / "config.txt").write_text("# fake boot partition\n")
        env = dict(os.environ)
        env["RASPARK_BOOT_DIR"] = str(boot)
        cmd = [sys.executable, str(DESKTOP_APP), "stage"]
        r1 = subprocess.run(cmd, capture_output=True, text=True,
                            env=env, timeout=60)
        check("Stage rc=0", r1.returncode == 0,
              r1.stderr.strip()[:200])
        check("Stage writes firstrun.sh",
              (boot / "firstrun.sh").exists())
        check("Stage writes the Pi payload",
              (boot / "raspberry_ark_pi.py").exists())
        hook = "systemd.run=/boot/firstrun.sh"
        cmdline = (boot / "cmdline.txt").read_text()
        check("Stage adds the systemd.run hook",
              hook in cmdline and "kernel-command-line.target"
              in cmdline, cmdline[:200])
        firstrun = (boot / "firstrun.sh").read_text()
        check("firstrun runs the Pi install + cleans its hook",
              "raspberry_ark_pi.py install" in firstrun
              and "sed -i" in firstrun, firstrun[:200])
        r2 = subprocess.run(cmd, capture_output=True, text=True,
                            env=env, timeout=60)
        cmdline2 = (boot / "cmdline.txt").read_text()
        check("Stage is idempotent (hook appears once)",
              r2.returncode == 0 and cmdline2.count(hook) == 1,
              cmdline2[:200])

    # --------------------------------------------------- hygiene
    blob = ""
    for name in ("raspberry_ark.py", "raspberry_ark_pi.py",
                 "build_installer.py", "README.md"):
        p = ROOT / name
        if p.exists():
            blob += p.read_text(errors="replace")
    piracy = "rom" + "hustler"  # needle built so it never appears here
    check("No ROM piracy site referenced anywhere",
          piracy not in blob.lower())
    check("No leftover easter egg in public copy",
          "saucy" + " pickle" not in blob)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("All smoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
