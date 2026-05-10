#!/usr/bin/env bash
set -euo pipefail

printf '\nMINIBUS Lite runtime installer\n'
printf 'This installer is for Linux runtime dependencies.\n'
printf 'Windows and macOS users should install Python 3 with Tkinter, then run tests/diagnostics manually.\n\n'

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y python3-tk pipewire-bin wireplumber
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3-tkinter pipewire-utils wireplumber
elif command -v pacman >/dev/null 2>&1; then
  sudo pacman -S --needed tk pipewire wireplumber
elif [[ "$(uname -s)" == "Darwin" ]]; then
  cat <<'MSG'
Detected macOS.
Install Python 3 with Tkinter support, then run:
  python3 -m unittest discover -s tests -v
  python3 diagnose_minibus.py
  python3 minibus.py

Optional for cleaner device listing:
  brew install switchaudio-osx

CoreAudio support in v0.4.0 is discovery-only; full patching is not implemented yet.
MSG
else
  cat <<'MSG'
No supported Linux package manager was detected.
Install these manually, then run ./run.sh:
  - Python 3
  - Python Tkinter
  - PipeWire command-line tools including pw-link and pw-loopback
  - WirePlumber or another PipeWire session manager

On Windows/macOS, v0.4.0 provides UI/tests/discovery only. Full audio patching is Linux/PipeWire only.
MSG
fi

printf '\nFinished. Run ./run.sh on Linux, or python3/py minibus.py on other platforms.\n'
