#!/bin/sh
# The Raspberry Ark - Linux starter.
# This file only makes sure Python 3 exists, then hands over to the
# universal installer (Raspberry-Ark-Setup.py), which detects your
# system and installs the Linux version of the app.
DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found - trying to install it ..."
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y python3
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm python
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y python3
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python could not be installed automatically."
  echo "Install python3 with your package manager, then run this file again."
  exit 1
fi

python3 "$DIR/Raspberry-Ark-Setup.py" "$@"
