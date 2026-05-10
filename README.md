![](./MINIBUS.png)

# MINIBUS Lite

MINIBUS Lite is a compact desktop-corner audio patch panel. It is designed for quick lane-based routing while staying small enough to live in the corner of a desktop.


MINIBUS is a **control plane**, not an audio engine. It does not process audio in Python. On Linux it asks PipeWire to create and remove audio links. On Windows and macOS it provides backend discovery, diagnostics, app launching, virtual-device-assisted route tracking, and a stable UI foundation for future native routing.

Current release: **v0.4.1 virtual-device route tracking update**  
Runtime: **Python 3 + Tkinter**  
Primary backend: **Linux PipeWire**  
Preview backends: **Windows WASAPI discovery + virtual route tracking**, **macOS CoreAudio discovery + virtual route tracking**  
License: **MIT**, see `LICENSE`.

## Important platform note

Linux/PipeWire is the only backend that currently performs native patching.

Windows and macOS do not expose a PipeWire-style graph that a small Python app can link with one command. MINIBUS can now track routes that use external virtual audio devices such as VB-CABLE, Voicemeeter, BlackHole, Loopback, or similar. In that mode, the virtual audio driver does the actual audio forwarding and MINIBUS stores the route state.

This is useful for real Windows/macOS workflows, but it is still not full native WASAPI/CoreAudio routing parity. Full native routing will require deeper platform backend code.

## Platform support

| Platform | Status | What works |
|---|---:|---|
| Linux Mint | Supported | Full PipeWire discovery, patch/off, bus creation, Learn mode. |
| Ubuntu / Debian | Supported | Full support when PipeWire and Tkinter are installed. |
| Fedora | Supported | Full support when PipeWire and Tkinter are installed. |
| Arch / Manjaro | Supported | Full support when PipeWire and Tkinter are installed. |
| Other PipeWire Linux | Likely | Run diagnostics first. |
| Linux PulseAudio only | Not supported | Use PipeWire/Pulse compatibility. |
| Linux JACK only | Not supported | Use PipeWire/JACK compatibility. |
| Windows | Preview | UI, tests, app launching, WASAPI endpoint discovery, virtual-device route tracking for VB-CABLE/Voicemeeter-style setups. No native WASAPI patching yet. |
| macOS | Preview | UI, tests, app launching, CoreAudio device discovery, virtual-device route tracking for BlackHole/Loopback-style setups. No native CoreAudio patching yet. |

## Repository layout

```text
README.md                         all documentation
LICENSE                           MIT license
.gitignore                        excludes caches and generated files
minibus.py                        main desktop app
run.sh                            Linux/macOS launcher script
install.sh                        Linux runtime dependency installer
install_desktop_launcher.sh       Linux desktop/menu launcher installer
diagnose_minibus.py               runtime diagnostic script
tests/test_minibus_core.py        unit tests
```

## Features

- Five compact patch lanes.
- Small vintage-style Tk desktop UI.
- Always-on-top toggle.
- Minimize and close buttons.
- Installed Linux app discovery through `.desktop` files.
- AppImage discovery in common user folders.
- Wine `.exe` discovery on Linux.
- Windows Start Menu / Program Files launcher discovery.
- macOS `.app` launcher discovery.
- Windows/macOS virtual-device route tracking for VB-CABLE, Voicemeeter, BlackHole, Loopback, and similar devices.
- Manual file picker for custom binaries, AppImages, EXEs, and app launchers.
- Learn mode for binding the next new audio port to a lane.
- Real MIC switch for MINIBUS-created mic/capture links on PipeWire.
- Real MONITOR switch for MINIBUS-created speaker/headphone links on PipeWire.
- Local diagnostics button.
- Terminal diagnostics script.
- Unit tests that users and contributors can run.
- No Rust, Node, npm, or Tauri build step.

## How routing works on Linux

The Linux backend uses standard PipeWire command-line tools:

```text
pw-link -o                 list output/source ports
pw-link -i                 list input/destination ports
pw-link SOURCE DEST        create a link
pw-link -d SOURCE DEST     remove a link
pw-loopback                create a virtual loopback bus
pw-dump                    diagnostics / graph visibility
```

The application launcher and the audio port are separate things. Selecting Firefox, Reaper, an AppImage, or a Windows `.exe` gives MINIBUS a way to start the program. The PipeWire audio port appears later, after that program opens audio or starts playback/capture.

Recommended workflow:

```text
choose launcher → run app → start audio → learn audio port → patch route
```

## Backend overview

### Linux: PipeWire backend

This is the production backend. It can list ports, create links, remove links, create loopback busses, run Learn mode, and enforce MIC/MONITOR switching for MINIBUS-created links.

### Windows: WASAPI preview backend

The Windows backend discovers audio endpoints through PowerShell and labels them as `WASAPI::Device Name`. It can also discover and launch Start Menu shortcuts and EXE files.

If a selected route uses a virtual audio endpoint such as VB-CABLE, Voicemeeter, or another virtual cable, MINIBUS can track the route as a virtual-device route. The external virtual driver performs the actual audio forwarding.

Current limitations:

- No native arbitrary app-to-app WASAPI patching yet.
- No native virtual bus creation yet.
- MIC/MONITOR controls can only manage MINIBUS-tracked routes.
- A future backend should integrate Windows audio session APIs and/or tighter virtual-device control.

### macOS: CoreAudio preview backend

The macOS backend discovers CoreAudio devices using `system_profiler`. If `SwitchAudioSource` is installed, MINIBUS can use it for cleaner device enumeration. It can also discover and launch `.app` bundles.

If a selected route uses a virtual audio endpoint such as BlackHole, Loopback, VB-CABLE, or another virtual cable, MINIBUS can track the route as a virtual-device route. The external virtual driver performs the actual audio forwarding.

Current limitations:

- No native arbitrary app-to-app CoreAudio patching yet.
- No native virtual bus creation yet.
- MIC/MONITOR controls can only manage MINIBUS-tracked routes.
- A future backend should integrate CoreAudio APIs and/or tighter virtual-device control.

## Install on Linux Mint, Ubuntu, Debian

Extract the release zip, then run:

```bash
cd ~/Desktop
unzip minibus-lite-v0.4.1.zip
cd minibus-lite-v0.4.1
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

## Install on Fedora

```bash
sudo dnf install -y python3-tkinter pipewire-utils wireplumber
./run.sh
```

## Install on Arch / Manjaro

```bash
sudo pacman -S --needed tk pipewire wireplumber
./run.sh
```

## Install on other Linux distributions

Install these packages using your distribution package manager:

- Python 3
- Python Tkinter
- PipeWire command-line tools including `pw-link`, `pw-loopback`, and `pw-dump`
- WirePlumber or another PipeWire session manager

Then run:

```bash
python3 minibus.py
```

## Run on Windows

Install Python 3 from the Microsoft Store or python.org. During install, enable the option to add Python to PATH if available.

From PowerShell inside the project folder:

```powershell
py -m unittest discover -s tests -v
py diagnose_minibus.py
py minibus.py
```

Expected result on Windows v0.4.1:

- The UI should open if Tkinter is available.
- Tests should run.
- Diagnostics should report the WASAPI backend.
- Audio endpoints may appear as `WASAPI::...`.
- If VB-CABLE, Voicemeeter, or a similar virtual driver is installed, diagnostics should identify virtual-looking endpoints.
- Patch/off can track routes that include a virtual audio endpoint.
- Non-virtual app-to-app patching will report that native WASAPI patching is not implemented yet.

## Run on macOS

Install Python 3. If Tkinter is missing from your Python build, install a Python distribution that includes Tk support.

From Terminal inside the project folder:

```bash
python3 -m unittest discover -s tests -v
python3 diagnose_minibus.py
python3 minibus.py
```

Optional helper for better CoreAudio device listing:

```bash
brew install switchaudio-osx
```

Expected result on macOS v0.4.1:

- The UI should open if Tkinter is available.
- Tests should run.
- Diagnostics should report the CoreAudio backend.
- Audio devices may appear as `CoreAudio::...`.
- If BlackHole, Loopback, VB-CABLE, or a similar virtual driver is installed, diagnostics should identify virtual-looking endpoints.
- Patch/off can track routes that include a virtual audio endpoint.
- Non-virtual app-to-app patching will report that native CoreAudio patching is not implemented yet.

## Virtual-device routing on Windows/macOS

MINIBUS can now track routes that include common virtual audio endpoints. This is the practical Windows/macOS path until native WASAPI/CoreAudio patching is implemented.

Typical Windows setup:

```text
App output → VB-CABLE / Voicemeeter virtual input → recorder / processor input
```

Typical macOS setup:

```text
App output → BlackHole / Loopback virtual device → recorder / processor input
```

Important distinction:

```text
MINIBUS tracks the route.
The virtual audio driver forwards the audio.
```

Use `audio` to refresh endpoints after installing a virtual device. Then select the virtual endpoint in a lane and press `patch`. If neither endpoint looks like a virtual device, MINIBUS will still report that native Windows/macOS patching is not implemented.

## Basic use on Linux/PipeWire

1. Start MINIBUS:

   ```bash
   ./run.sh
   ```

2. Press `apps` to scan installed apps, AppImages, and Wine `.exe` locations.

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

A normal browser or media player is often source-only. It can start a route, but it usually cannot sit in the middle of a processing chain. A middle app needs both input and output ports. DAWs, plugin hosts, filter nodes, virtual busses, and loopback nodes are better middle-chain choices.

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

## Creating virtual busses on Linux

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

Run diagnostics from the project folder:

```bash
python3 diagnose_minibus.py
```

The normal diagnostic checks:

- Python version
- Tkinter availability
- detected platform/backend
- PipeWire tools and services on Linux
- PowerShell endpoint discovery on Windows
- CoreAudio device discovery on macOS
- visible audio ports/devices
- virtual audio endpoint detection on Windows/macOS
- app launcher discovery
- core unit tests

The normal diagnostic does not change audio routing.

## Optional live PipeWire bus test

On Linux/PipeWire only:

```bash
python3 diagnose_minibus.py --bus-test
```

This briefly creates a temporary `pw-loopback` bus, checks whether PipeWire can see it, then stops it.

## Unit tests

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

The unit tests do not require a live PipeWire, WASAPI, or CoreAudio graph. They use mocks for command execution and check parsing, launcher discovery, route validation, saved config handling, MIC/MONITOR heuristics, command wrappers, and backend selection.

Before opening a bug report, include this output:

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

For Windows/macOS preview testing:

1. Run the unit tests.
2. Run diagnostics.
3. Start the UI.
4. Confirm launcher discovery works.
5. Confirm endpoints/devices are visible where possible.
6. If a virtual audio driver is installed, confirm a route using that endpoint can be patched and shown in the link inspector.
7. Confirm non-virtual native patching returns a clear message rather than crashing.

## Configuration

MINIBUS saves UI state in the platform user config directory:

```text
Linux:   ~/.config/minibus/config.json
macOS:   ~/Library/Application Support/MINIBUS/config.json
Windows: %APPDATA%\MINIBUS\config.json
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

Linux:

```bash
rm -f ~/.config/minibus/config.json
```

macOS:

```bash
rm -f "$HOME/Library/Application Support/MINIBUS/config.json"
```

Windows PowerShell:

```powershell
Remove-Item "$env:APPDATA\MINIBUS\config.json" -ErrorAction SilentlyContinue
```

## Troubleshooting

### No ports are visible on Linux

Run:

```bash
pw-link -o
pw-link -i
systemctl --user status pipewire wireplumber
python3 diagnose_minibus.py
```

Make sure PipeWire and WirePlumber are running in your user session.

### App does not appear in audio ports

Start playback, open the app's audio engine, or select an audio device inside the app. Many programs create no audio ports while idle.

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

### Windows `.exe` does not launch on Linux

Install Wine and test manually:

```bash
wine /path/to/app.exe
```

If Wine cannot launch the app outside MINIBUS, MINIBUS cannot launch it either.

### Windows/macOS route does not produce audio

Check that the route includes a real virtual audio device such as VB-CABLE, Voicemeeter, BlackHole, or Loopback. MINIBUS only tracks the route; the external virtual driver must be installed and selected in the source/target applications.

If the app itself has an audio device selector, choose the virtual input/output there as well. Then press `audio` in MINIBUS to refresh device discovery.

### MIC or MONITOR did not disconnect something

MINIBUS intentionally avoids disconnecting arbitrary system links. It only manages links it created or saved in its lanes. This protects unrelated desktop audio.

### The UI opens too tall or in the wrong place

Reset saved state:

```bash
rm -f ~/.config/minibus/config.json
./run.sh
```

### Permission errors on Linux

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
zip -r minibus-lite-v0.4.1.zip minibus-lite-v0.4.1 \
  -x '*/__pycache__/*' '*/.git/*' '*.pyc' '*/.pytest_cache/*'
```

## Contributing

Contributions are welcome. Good first areas:

- Friendlier audio port names.
- Favourites in the app chooser.
- Per-lane auto-reconnect.
- Better visible link inspector.
- Named scene save/load.
- Stronger virtual bus lifecycle management.
- Real Windows WASAPI routing backend.
- Real macOS CoreAudio routing backend.

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

### v0.4.1

- Added virtual-device route tracking for Windows/macOS preview backends.
- Added virtual audio endpoint detection in diagnostics.
- Improved unsupported-route messages for native WASAPI/CoreAudio routes.
- Updated Windows config storage to use `%APPDATA%\MINIBUS`.
- Updated macOS config storage to use `~/Library/Application Support/MINIBUS`.
- Added unit tests for virtual-device route tracking.

### v0.4.0

- Added backend selection for Linux, Windows, and macOS.
- Kept Linux PipeWire as the full routing backend.
- Added WASAPI endpoint discovery on Windows.
- Added CoreAudio device discovery on macOS.
- Added Windows launcher discovery for Start Menu shortcuts and EXEs.
- Added macOS `.app` launcher discovery.
- Added clear unsupported-route messages on preview backends.
- Added cross-platform backend unit tests.

### v0.3.2

- Consolidated all project documentation into one `README.md`.
- Kept `LICENSE` as the separate legal file.
- Added clearer platform guidance.

### v0.3.1

- Removed vertical empty space from the main UI.
- Clamped saved tall window geometry to a compact patch-strip height.
- Kept the panel horizontally resizable while preserving a compact vertical layout.

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
- Better link inspector.
- Named scene save/load.
- Stronger virtual bus management.

Cross-platform roadmap:

- Move routing code into dedicated backend modules.
- Add a proper `backend-linux-pipewire` module.
- Expand `backend-windows-wasapi` beyond discovery.
- Expand `backend-macos-coreaudio` beyond discovery.
- Expand virtual-driver integration beyond route tracking.
- Keep the same lane UI and config format across all platforms.
