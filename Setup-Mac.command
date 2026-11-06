#!/bin/sh
# The Raspberry Ark - macOS starter.
# This file only makes sure Python 3 exists, then hands over to the
# universal installer (Raspberry-Ark-Setup.py), which detects your
# system and installs the macOS version of the app.
DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found - installing it from python.org ..."
  PKG="/tmp/python-macos.pkg"
  if curl -fL "https://www.python.org/ftp/python/3.15.2/python-3.15.2-macos11.pkg" -o "$PKG"; then
    echo "macOS will ask for your password to install Python."
    sudo installer -pkg "$PKG" -target /
    rm -f "$PKG"
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python could not be installed automatically."
  echo "Get it free from https://www.python.org/downloads/ then run this file again."
  read -n 1 -s -r -p "Press any key to close."
  exit 1
fi

python3 "$DIR/Raspberry-Ark-Setup.py" "$@"
echo
echo "Press any key to close."
read -n 1 -s
