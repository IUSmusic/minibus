![minibus](./MINIBUS.png)

# MINIBUS Lite

MINIBUS Lite is a compact desktop patch panel for PipeWire audio routing. It is designed to sit in a corner of the desktop and provide fast lane-based routing without acting as the audio engine itself.


MINIBUS does **not** process audio in Python. It is a control plane. PipeWire moves the audio; MINIBUS discovers ports and asks PipeWire to create or remove links.

Current release: **v0.3.2 docs-ready release**  
Runtime: **Python 3 + Tkinter + PipeWire CLI tools**  
License: **MIT**, see `LICENSE`.

## Project status

MINIBUS Lite is currently a Linux PipeWire application.

The app can be started on any platform with Python/Tkinter, but the audio routing backend currently depends on Linux PipeWire tools such as `pw-link`, `pw-loopback`, and `pw-dump`. On Windows and macOS, the UI/tests may run, but real audio patching is not expected to work until native WASAPI/CoreAudio backends are added.

## Platform support

| Platform | Status | Notes |
|---|---:|---|
| Linux Mint | Supported | Primary target. |
| Ubuntu / Debian | Supported | Requires PipeWire and Tkinter. |
| Fedora | Supported | Requires PipeWire and Tkinter. |
| Arch / Manjaro | Supported | Requires PipeWire and Tkinter. |
| Other PipeWire Linux | Likely | Run diagnostics first. |
| Linux PulseAudio only | Not supported | Use PipeWire/Pulse compatibility. |
| Linux JACK only | Not supported | Use PipeWire/JACK compatibility. |
| Windows | UI/tests only | Needs future WASAPI backend. |
| macOS | UI/tests only | Needs future CoreAudio backend. |

## What MINIBUS does

MINIBUS provides five compact patch lanes. Each lane can launch apps, learn newly appearing PipeWire ports, create links, disconnect links, and respect the global MIC and MONITOR switches.

Main features:

- Five desktop-corner patch lanes.
- Installed Linux app discovery through `.desktop` files.
- AppImage discovery in common user folders.
- Wine `.exe` discovery in common Wine folders.
- Manual file picker for custom binaries, AppImages, and `.exe` files.
- Learn mode for binding the next new PipeWire stream to a lane.
- Real MIC switch for MINIBUS-created mic/capture links.
- Real MONITOR switch for MINIBUS-created speaker/headphone links.
- Local diagnostics button in the UI.
- Terminal diagnostics script.
- Unit tests that users and contributors can run.
- No Rust, Node, npm, or Tauri build step.

## How the routing works

MINIBUS uses standard PipeWire command-line tools:

- `pw-link -o` lists output/source ports.
- `pw-link -i` lists input/destination ports.
- `pw-link SOURCE DESTINATION` creates a link.
- `pw-link -d SOURCE DESTINATION` removes a link.
- `pw-loopback` creates temporary or named virtual loopback busses.
- `pw-dump` is used by diagnostics to check graph visibility.

The application launcher and the audio port are separate things. Selecting Firefox, Reaper, an AppImage, or a Windows `.exe` only gives MINIBUS a way to start the program. The PipeWire audio port appears later, after that program opens audio or starts playback/capture.

Recommended mental model:

```text
choose launcher → run app → start audio → learn PipeWire port → patch route
```

## Repository layout

```text
minibus.py                       main desktop app
run.sh                           start the app
install.sh                       install runtime dependencies on common Linux distros
install_desktop_launcher.sh       install a local desktop/menu launcher
diagnose_minibus.py              runtime diagnostic script
tests/                           unit tests
README.md                        all documentation
LICENSE                          MIT license
.gitignore                       excludes local caches and generated files
```

## Installation on Linux Mint, Ubuntu, Debian

Extract the release zip, then install runtime dependencies:

```bash
cd ~/Desktop
unzip minibus-lite-v0.3.2.zip
cd minibus-lite-v0.3.2
./install.sh
./run.sh
```

Equivalent manual dependency install:

```bash
sudo apt update
sudo apt install -y python3-tk pipewire-bin wireplumber
```

Then run:

```bash
./run.sh
```

## Installation on Fedora

```bash
sudo dnf install -y python3-tkinter pipewire-utils wireplumber
./run.sh
```

## Installation on Arch / Manjaro

```bash
sudo pacman -S --needed tk pipewire wireplumber
./run.sh
```

## Installation on other Linux distributions

Install these requirements with your distribution package manager:

- Python 3
- Python Tkinter
- PipeWire command-line tools including `pw-link`, `pw-loopback`, and `pw-dump`
- WirePlumber or another PipeWire session manager

Then run:

```bash
./run.sh
```

If the app opens but no audio ports appear, run:

```bash
python3 diagnose_minibus.py
```

## Optional Wine support for Windows `.exe` apps on Linux

MINIBUS can list and launch Windows `.exe` files through Wine on Linux. It does not run `.exe` files natively.

On Debian/Ubuntu/Mint:

```bash
sudo apt install -y wine
```

Then test Wine manually:

```bash
wine /path/to/app.exe
```

After the app starts and creates audio, use MINIBUS Learn mode to bind the new PipeWire stream.

## Optional AppImage support

AppImages must be executable before MINIBUS can launch them:

```bash
chmod +x /path/to/App.AppImage
```

MINIBUS scans common user folders for AppImages, but you can always choose one with `Locate file…`.

## Desktop/menu launcher

From inside the extracted project folder:

```bash
./install_desktop_launcher.sh
```

This creates a user-local launcher at:

```text
~/.local/share/applications/minibus-lite.desktop
```

The launcher points to the current extracted folder. If you move the folder later, run `./install_desktop_launcher.sh` again.

## Running on Windows

The current release is not a Windows audio router.

You can run the Python unit tests on Windows if Python is installed, but full audio patching requires a future backend using Windows audio APIs such as WASAPI.

To run tests only on Windows PowerShell:

```powershell
py -m unittest discover -s tests -v
```

The app itself may open if Tkinter is available:

```powershell
py minibus.py
```

Expected limitations on Windows:

- `pw-link` is missing.
- `pw-loopback` is missing.
- PipeWire ports are unavailable.
- Patch, MIC, and MONITOR routing actions will not control Windows audio.

Windows support roadmap:

- Add a `backend-windows-wasapi` module.
- Keep the lane UI and saved scene format.
- Replace PipeWire link commands with WASAPI/session routing where possible.

## Running on macOS

The current release is not a macOS audio router.

You can run the Python unit tests on macOS if Python/Tkinter is installed. Full audio patching requires a future backend using CoreAudio.

To run tests only:

```bash
python3 -m unittest discover -s tests -v
```

The app may open if Tkinter is available:

```bash
python3 minibus.py
```

Expected limitations on macOS:

- `pw-link` is missing.
- `pw-loopback` is missing.
- PipeWire ports are unavailable.
- Patch, MIC, and MONITOR routing actions will not control CoreAudio.

macOS support roadmap:

- Add a `backend-macos-coreaudio` module.
- Keep the lane UI and saved scene format.
- Replace PipeWire link commands with CoreAudio device/session routing where possible.

## Basic use

1. Start MINIBUS:

   ```bash
   ./run.sh
   ```

2. Press `apps` to scan installed apps, AppImages, and quick Wine `.exe` locations.

3. Click an `app` button in a lane.

4. Choose an installed app, AppImage, `.exe`, or `Locate file…`.

5. Press `run` on that lane.

6. Make the app produce audio. Many programs do not appear in PipeWire until playback or capture starts.

7. Press `learn` on the lane.

8. MINIBUS watches for the next new PipeWire port and fills the lane automatically.

9. Choose a destination/output port.

10. Press `patch` to connect the lane.

11. Press `off` to disconnect that lane.

## Lane slots explained

Each lane is visually shaped like this:

```text
source/input → app launcher → app launcher → app launcher → destination/output
```

The `app` buttons are launchers. They are not necessarily audio ports.

A normal media player or browser is often source-only. It can start a route, but it usually cannot sit in the middle of a processing chain. A middle app needs both input and output ports. DAWs, plugin hosts, filter nodes, virtual busses, and loopback nodes are better middle-chain choices.

Examples:

```text
Firefox → Record Bus → Speakers
Mic → Noise Suppressor → Reaper → Monitor Bus
Synth App → Reaper Input → Speakers
Discord → Voice Bus → Recorder
```

## Learn mode

Learn mode is the most reliable way to bind strange apps, AppImages, and Wine apps.

Use it like this:

```text
click lane learn → start audio in the app → MINIBUS detects the new PipeWire port
```

If Learn mode times out:

- Start playback or enable the app audio engine first.
- Press `audio` to refresh ports.
- Press `learn` again.
- Check diagnostics if no ports appear.

## MIC switch

The MIC switch is conservative. It only affects MINIBUS-created or MINIBUS-saved mic/capture links.

`MIC OFF`:

- Disconnects MINIBUS-created links from ports that look like microphones or capture sources.
- Blocks new mic/capture patches from MINIBUS lanes.
- Does not destroy unrelated system links.

`MIC ON`:

- Allows mic/capture patches.
- Reconnects saved MINIBUS mic/capture links when possible.

This is intended as a route-level mic kill inside MINIBUS, not as a full system privacy control.

## MONITOR switch

The MONITOR switch is also conservative. It only affects MINIBUS-created or MINIBUS-saved monitor links.

`MONITOR OFF`:

- Disconnects MINIBUS-created links to ports that look like speakers, headphones, or monitor playback targets.
- Blocks new monitor patches from MINIBUS lanes.
- Keeps non-monitor routes alive where possible.

`MONITOR ON`:

- Allows monitor patches.
- Reconnects saved monitor links when possible.

This lets you stop hearing a route while keeping a recording or bus route alive.

## Creating virtual busses

Use `bus +` to create a PipeWire loopback bus. Virtual busses are useful for browser-to-recorder routing, DAW sends, monitor control, and duplicate routing.

Examples:

```text
Record Bus
Monitor Bus
Voice Bus
DAW Send
```

If a bus does not appear immediately, press `audio` after a second or two. PipeWire/WirePlumber can take a moment to publish new nodes.

## Diagnostics

Run local diagnostics from the project folder:

```bash
python3 diagnose_minibus.py
```

The normal diagnostic checks:

- Python version
- Tkinter availability
- `pw-link`
- `pw-loopback`
- `pw-dump`
- Wine availability, if installed
- PipeWire user service status
- WirePlumber user service status
- visible PipeWire ports
- app/AppImage/EXE launcher discovery
- core unit tests

The normal diagnostic does not change audio routing.

## Optional live PipeWire bus test

For a stronger local check:

```bash
python3 diagnose_minibus.py --bus-test
```

This briefly creates a temporary `pw-loopback` bus, checks whether PipeWire can see it, then stops it. Use this on a real PipeWire desktop session.

## Unit tests

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

The unit tests do not require a live PipeWire graph. They use mocks for command execution and check parsing, launcher discovery, route validation, saved config handling, MIC/MONITOR heuristics, and command-wrapper behaviour.

Before opening a bug report, ask users to include this output:

```bash
python3 -m unittest discover -s tests -v
python3 diagnose_minibus.py
```

## Manual smoke test before release

Before publishing a new release, test on a real Linux PipeWire desktop:

1. Run `python3 -m py_compile minibus.py diagnose_minibus.py`.
2. Run `python3 -m unittest discover -s tests -v`.
3. Run `python3 diagnose_minibus.py`.
4. Optionally run `python3 diagnose_minibus.py --bus-test`.
5. Start MINIBUS with `./run.sh`.
6. Confirm the window opens, moves, minimizes, closes, and toggles topmost.
7. Press `diag` and confirm required checks pass.
8. Press `apps` and confirm installed apps appear.
9. Launch an audio app through a lane.
10. Start audio and press `learn`.
11. Patch to a monitor/output destination.
12. Toggle `MONITOR` off and back on.
13. If testing a mic route, toggle `MIC` off and back on.
14. Quit and reopen. Confirm saved lane/window state returns.

## Configuration

MINIBUS saves UI state here:

```text
~/.config/minibus/config.json
```

This stores:

- window position
- lane source/destination selections
- selected launchers
- MIC state
- MONITOR state
- topmost setting
- auto-refresh setting

To reset MINIBUS state:

```bash
rm -f ~/.config/minibus/config.json
```

## Troubleshooting

### No ports are visible

Run:

```bash
pw-link -o
pw-link -i
systemctl --user status pipewire wireplumber
python3 diagnose_minibus.py
```

Make sure PipeWire and WirePlumber are running in your user session.

### App does not appear in audio ports

Start playback, open the app's audio engine, or select an audio device inside the app. Many programs create no PipeWire ports while idle.

Then press:

```text
audio
learn
```

### AppImage does not launch

Make it executable:

```bash
chmod +x /path/to/App.AppImage
```

Then test it manually:

```bash
/path/to/App.AppImage
```

### Windows `.exe` does not launch

Install Wine and test manually:

```bash
wine /path/to/app.exe
```

If Wine cannot launch the app outside MINIBUS, MINIBUS cannot launch it either.

### MIC or MONITOR did not disconnect something

MINIBUS intentionally avoids disconnecting arbitrary system links. It only manages links it created or saved in its lanes. This protects unrelated desktop audio.

### The UI opens too tall or in the wrong place

Reset saved state:

```bash
rm -f ~/.config/minibus/config.json
./run.sh
```

### Permission errors

Do not run MINIBUS with `sudo`. PipeWire desktop audio usually runs in the normal user session. Running as root can make user audio ports invisible.

## GitHub release packaging

A clean source zip should include:

```text
README.md
LICENSE
.gitignore
minibus.py
diagnose_minibus.py
install.sh
run.sh
install_desktop_launcher.sh
tests/test_minibus_core.py
```

It should not include:

```text
__pycache__/
.pytest_cache/
.git/
*.pyc
local config files
build output
```

Build a clean zip from the parent folder:

```bash
cd ..
zip -r minibus-lite-v0.3.2.zip minibus-lite-v0.3.2 \
  -x '*/__pycache__/*' '*/.git/*' '*.pyc' '*/.pytest_cache/*'
```

## Contributing

Contributions are welcome. Good first areas:

- Better PipeWire port name cleanup.
- More reliable app/AppImage discovery.
- Favourites in the app chooser.
- Per-lane auto-reconnect.
- Safer bus lifecycle management.
- A structured backend interface for future Windows/macOS support.

Development checks:

```bash
python3 -m py_compile minibus.py diagnose_minibus.py
python3 -m unittest discover -s tests -v
python3 diagnose_minibus.py
```

For pull requests, include:

- What changed.
- Which platform was tested.
- Output from the unit tests.
- Output from `diagnose_minibus.py` when the change affects routing or discovery.

## Changelog

### v0.3.2

- Consolidated all project documentation into this single `README.md`.
- Kept `LICENSE` as the only separate documentation/legal file.
- Added clearer platform support guidance for Linux, Windows, and macOS.
- Added release packaging, diagnostics, testing, troubleshooting, and contribution guidance in one place.

### v0.3.1

- Removed vertical empty space from the main UI.
- Clamped saved tall window geometry to a compact patch-strip height.
- Kept the panel horizontally resizable while preserving a compact vertical layout.
- Added tests for compact geometry behaviour.

### v0.3.0

- Added saved configuration in `~/.config/minibus/config.json`.
- Improved compact layout.
- Added release documentation and GitHub-ready project files.
- Improved background audio refresh.

### v0.2.0

- Added Learn mode.
- Added real MIC and MONITOR link switching for MINIBUS-created links.
- Added local diagnostics button.
- Added terminal diagnostic script.
- Added core unit tests.

## Roadmap

Near-term Linux roadmap:

- Favourites list.
- Per-lane auto mode.
- Friendlier source/destination names.
- Better visible link inspector.
- Named scene save/load.
- Stronger virtual bus management.

Cross-platform roadmap:

- Keep the lane UI and config model.
- Split routing into backend modules.
- Add `backend-linux-pipewire`.
- Add `backend-windows-wasapi`.
- Add `backend-macos-coreaudio`.
