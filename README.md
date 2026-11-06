# The Raspberry Ark

**One toolkit that takes a blank microSD card to a Raspberry Pi that
boots straight into RetroArch.** By **Delukz**.

The Raspberry Ark merges two tools into a single package with two
halves:

- **Desktop half** (Windows / macOS / Linux) — prepares the SD card,
  downloads and flashes Raspberry Pi OS, and stages the second half
  onto the card.
- **Pi half** (runs on the Raspberry Pi) — installs RetroArch and the
  right libretro cores for your Pi model, writes the config
  (including netplay), creates your Games Library, and sets the Pi
  to auto-boot into RetroArch.

![The Raspberry Ark emblem](assets/emblem.png)

## The pipeline

The steps run **in this order** — the desktop app's `pipeline`
command walks you through them one at a time:

1. **Prep** — the card is detected and formatted / wiped.
2. **Flash** — Raspberry Pi OS is downloaded from the official
   Raspberry Pi feed (the same `os_list` feed the official Imager
   uses), SHA-256-verified, extracted, and written to the card with
   the built-in writer (or balenaEtcher, downloaded from its
   official GitHub releases, if you prefer).
3. **Stage** — the Pi half is written onto the card's boot
   partition with a first-boot hook (details below).
4. **On the Pi** — at first boot the Pi installs RetroArch itself:
   model/OS detection, tiered cores, tuned config, netplay setup,
   Games Library folders, auto-boot — then reboots into RetroArch.

### How staging works (and why)

Staging uses the **Raspberry Pi Imager mechanism**: the app writes
`raspberry_ark_pi.py` and a `firstrun.sh` script onto the card's FAT
boot partition and appends the Imager's hook to `cmdline.txt`:

```
systemd.run=/boot/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target
```

On first boot, systemd runs `firstrun.sh` as root. It copies the Pi
app into the first user's home, runs the full install as that user,
strips the hook back out of `cmdline.txt` (both the old `/boot` and
the Bookworm `/boot/firmware` layouts), deletes itself, and reboots
into the finished system.

Why this route instead of installing onto the card from the desktop?
The Pi's ext4 root partition can't be written from Windows or macOS
without third-party drivers, and running ARM package installs from a
desktop is unreliable. The firstrun mechanism is what Raspberry Pi's
own Imager uses, it works on every Pi OS release since Bullseye, and
the install runs natively on the Pi. If the boot partition can't be
found (say you flashed with another tool), the `stage` command
prints exact manual fallback steps — including the simplest one:
copy `raspberry_ark_pi.py` to the Pi yourself and run it there.

## Install

Desktop (Windows / macOS / Linux):

```sh
bash Setup-Linux.sh        # or Setup-Mac.command / Setup-Windows.bat
```

…or directly: `python3 Raspberry-Ark-Setup.py`

On a Raspberry Pi (Pi OS already running):

```sh
bash Setup-Pi.sh
```

The universal installer detects where it's running: desktops get the
desktop half (`raspberry-ark` command), a Pi gets the Pi half
(`raspberry-ark-pi` command) and an offer to install RetroArch
immediately. In the install folders you'll also find the emblem
(`assets/emblem.png`), used as the app icon.

## Desktop half — commands

```sh
raspberry-ark             # menu
raspberry-ark pipeline    # prep -> flash -> stage, in order
raspberry-ark download    # download Raspberry Pi OS (checksum-verified)
raspberry-ark extract     # extract the .img.xz (checksum-verified)
raspberry-ark etcher      # download + unpack balenaEtcher
raspberry-ark flash       # built-in SD writer
raspberry-ark flash-etcher# flash guided by Etcher
raspberry-ark format      # format / wipe a card (FAT32/exFAT/EXT4)
raspberry-ark stage       # stage the first-boot installer on a card
raspberry-ark sizes       # image sizes vs the 10 GB budget
raspberry-ark uninstall   # remove downloaded OS + Etcher
```

microSD: **8 GB minimum, 16 GB recommended** (32 GB ideal).

## Pi half — commands

```sh
raspberry-ark-pi            # menu
raspberry-ark-pi detect     # model / OS / compatibility report
raspberry-ark-pi install    # RetroArch + cores + config + auto-boot
raspberry-ark-pi config     # rewrite the RetroArch config
raspberry-ark-pi netplay [relay-host]  # (re)write netplay settings
raspberry-ark-pi autoboot   # set up auto-boot into RetroArch
raspberry-ark-pi library    # Games Library guidance
raspberry-ark-pi uninstall  # remove Ark config + library folders
raspberry-ark-pi --dry-run install   # print every step, change nothing
```

### Cores by tier

| Pi model | Tier | Cores |
|----------|------|-------|
| Pi 5, Pi 4, Pi 400, CM4 | A | Everything incl. PS1 + N64 |
| Pi 3 / 3B+ / 3A+, Zero 2 W | B | Everything incl. PS1 |
| Pi 2 | C | 8/16-bit set |
| Pi 1, Zero, Zero W | D | Lightest set, with warnings |
| Anything else | — | Refuses (unless `--force`) |

Every tier includes **SNES (libretro-snes9x)**, Game Boy/Color
(gambatte), NES (nestopia), GBA (mgba), Genesis/Master System/Game
Gear (genesisplusgx) and Atari (stella/prosystem) where the tier
allows. **PlayStation (libretro-pcsx-rearmed)** is included on Pi 3
and up (tiers A and B). All packages come from the official
Raspberry Pi OS / Debian repositories at install time.

### Auto-boot

After install, every boot goes straight into RetroArch — **without
loading the desktop**. Method: `raspi-config nonint
do_boot_behaviour B2` (official console autologin) plus a
marker-delimited block in `~/.bash_profile` that launches
`retroarch --fullscreen` when the autologin shell lands on tty1.
RetroArch's gl/vulkan drivers run directly on KMS/DRM from the
console (the same way RetroPie launches), so no X/Wayland session
is needed; quitting RetroArch drops you back at the terminal
prompt. Remove it any time with `raspberry-ark-pi uninstall`
(which also strips the `.bash_profile` block).

### Netplay

The written `retroarch.cfg` includes netplay on **port 55435**
(`netplay_ip_port`), a nickname, and the relay fields
(`netplay_use_mitm_server`, `netplay_mitm_server`). Host or join
from RetroArch's Netplay menu — direct by IP on your network, or,
for internet play without port-forwarding, enable the relay (MITM)
server option, which uses RetroArch's built-in free public
lobby/relay service. `raspberry-ark-pi netplay <relay-host>` pins a
specific relay host if you run your own.

## Games Library

The Pi half creates `~/RaspberryArk/roms/<system>` folders (plus
`saves`, `states` and `system` for BIOS files). **No games and no
BIOS files are included or downloaded.** Legal ways to fill it:

- **Homebrew and public-domain ROMs** — games released free by their
  creators: Homebrew Hub, PDRoms, and itch.io homebrew (NES / Game
  Boy / Genesis homebrew sold or given away by its developers).
- **Your own legally-owned backups** — dump cartridges and discs you
  own and copy the files in.

## Tests

No Pi and no SD card needed — detection runs off fixtures, installs
are dry-run, staging runs against a fake boot partition:

```sh
python3 tests/smoke_test.py
```

## Developer

Built by **Delukz** — The Raspberry Ark v1.0.0 (2026), MIT-licensed
(see `LICENSE`). Raspberry Pi OS, balenaEtcher, RetroArch and the
libretro cores are downloaded/installed from their official sources
at run time and remain under their own licenses.
