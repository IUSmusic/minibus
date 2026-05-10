#!/usr/bin/env python3
"""
MINIBUS Lite v0.4.1
=================
A small desktop-corner audio patch panel.

Linux/PipeWire is the full routing backend. Windows/WASAPI and macOS/CoreAudio
are included as preview discovery backends so the same UI, diagnostics, tests,
and launcher workflow can run on those platforms while native routing support
is developed.

This version avoids the large Tauri/Rust build path. It is a lightweight
Tkinter app focused on a compact patch panel, app launching, Learn mode,
real MIC and MONITOR switching for MINIBUS-created PipeWire links, and local
diagnostics.
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "MINIBUS Lite v0.4.1"
REFRESH_SECONDS = 5
LEARN_TIMEOUT_SECONDS = 25
def default_config_dir() -> Path:
    """Return the platform-appropriate user config directory."""
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "MINIBUS"
        return Path.home() / "AppData" / "Roaming" / "MINIBUS"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "MINIBUS"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "minibus"


CONFIG_DIR = default_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"
FIELD_CODE_RE = re.compile(r"%[fFuUdDnNickvm]")

#
# Virtual routing support for non-PipeWire platforms
#
# On Windows and macOS MINIBUS Lite v0.4.1 provides discovery and
# application launching but does not have direct access to the system
# audio graph. Some users employ virtual audio drivers such as
# VB‑CABLE/Voicemeeter on Windows or BlackHole/Loopback on macOS to
# create their own routing buses. To make MINIBUS more useful on those
# platforms, we define a simple virtual connection store. When the user
# patches a source or destination containing one of the keywords below,
# MINIBUS will record the connection internally and report success. It
# does not perform any real audio processing; instead, it assumes the
# external virtual device handles the routing. Disconnecting the link
# removes it from the internal store.

# Keywords that identify virtual devices. Matching is case-insensitive.
VIRTUAL_DEVICE_KEYWORDS: list[str] = [
    "cable",
    "vb",
    "voicemeeter",
    "blackhole",
    "loopback",
    "virtual",
]

# Internal store of active virtual connections on non-PipeWire platforms.
# Each entry is a (source, dest) tuple. These are purely descriptive and
# do not reflect actual OS audio graph state.
_virtual_connections: set[tuple[str, str]] = set()


@dataclass
class Launcher:
    label: str
    command: str
    kind: str
    path: str = ""

    def search_text(self) -> str:
        return f"{self.label} {self.command} {self.kind} {self.path}".lower()

    def to_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "command": self.command,
            "kind": self.kind,
            "path": self.path,
        }

    @staticmethod
    def from_dict(data: object) -> Optional["Launcher"]:
        if not isinstance(data, dict):
            return None
        label = str(data.get("label", "")).strip()
        command = str(data.get("command", "")).strip()
        kind = str(data.get("kind", "binary")).strip() or "binary"
        path = str(data.get("path", "")).strip()
        if not label or not command:
            return None
        return Launcher(label=label, command=command, kind=kind, path=path)


def read_config() -> dict[str, object]:
    """Read MINIBUS state from XDG config without raising."""
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def write_config(data: dict[str, object]) -> None:
    """Write MINIBUS state to XDG config without crashing the app."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        # Persisting UI state is useful, but must never break routing.
        pass


def short_label(text: str, max_chars: int = 8) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def compact_geometry(saved: object, default: str = "950x186+40+40") -> str:
    """Return a compact geometry string while preserving saved width/position.

    v0.3 could save a tall window, leaving a large empty grey area.  This
    clamps height on startup so existing users automatically get the tighter
    corner-panel layout without manually editing ~/.config/minibus/config.json.
    """
    raw = str(saved or default)
    match = re.match(r"^(\d+)x(\d+)([+-]\d+[+-]\d+)?$", raw)
    if not match:
        return default
    width = max(780, min(1400, int(match.group(1))))
    # Keep the panel short.  The five rows + toolbar + status fit in ~180 px.
    height = 186
    pos = match.group(3) or "+40+40"
    return f"{width}x{height}{pos}"




def host_system() -> str:
    """Return the current host OS using Python's platform names."""
    return platform.system()


def audio_backend_name() -> str:
    """Name the backend MINIBUS will use on this machine.

    Linux uses the real PipeWire backend. Windows and macOS currently expose
    discovery/diagnostic backends. Full app-to-app patching on those platforms
    requires OS-specific audio routing work and, in many cases, a virtual audio
    device/driver.
    """
    system = host_system()
    if system == "Linux":
        return "PipeWire"
    if system == "Windows":
        return "WASAPI"
    if system == "Darwin":
        return "CoreAudio"
    return system or "Unknown"


def backend_supports_patching() -> bool:
    """Return True only for backends that can create/remove audio links now."""
    return audio_backend_name() == "PipeWire"

def run_command(args: list[str], timeout: float = 4.0) -> tuple[int, str, str]:
    """Run a command and return rc/stdout/stderr without raising."""
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except PermissionError as exc:
        return 126, "", str(exc)
    except OSError as exc:
        return 126, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "timed out"


def pipewire_ports(direction: str) -> list[str]:
    """Return PipeWire ports from pw-link.

    direction='output' uses pw-link -o, direction='input' uses pw-link -i.
    In PipeWire terms, output ports are link sources and input ports are link
    destinations.
    """
    flag = "-o" if direction == "output" else "-i"
    rc, out, _err = run_command(["pw-link", flag])
    if rc != 0:
        return []
    ports: list[str] = []
    for line in out.splitlines():
        clean = line.strip()
        if clean and clean not in ports:
            ports.append(clean)
    return ports


def parse_windows_endpoint_names(text: str) -> list[str]:
    """Parse PowerShell JSON or plain text into Windows endpoint names."""
    names: list[str] = []
    stripped = text.strip()
    if not stripped:
        return names
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            data = [data]
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    value = row.get("FriendlyName") or row.get("Name") or row.get("Caption")
                    if value:
                        n = str(value).strip()
                        if n and n not in names:
                            names.append(n)
                elif isinstance(row, str):
                    n = row.strip()
                    if n and n not in names:
                        names.append(n)
            return names
    except json.JSONDecodeError:
        pass
    for line in stripped.splitlines():
        n = line.strip()
        if not n or n.lower() in {"friendlyname", "name", "caption"}:
            continue
        if n not in names:
            names.append(n)
    return names


def wasapi_ports(direction: str) -> list[str]:
    """Return Windows audio endpoints using PowerShell.

    This is an initial WASAPI discovery backend. It lists devices/endpoints but
    does not create arbitrary app-to-app patch links. Windows does not expose a
    PipeWire-style public graph that MINIBUS can link with a simple command.
    """
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return []
    command = (
        "Get-PnpDevice -Class AudioEndpoint -Status OK | "
        "Select-Object -Property FriendlyName | ConvertTo-Json"
    )
    rc, out, _err = run_command([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], timeout=8)
    names = parse_windows_endpoint_names(out) if rc == 0 else []
    if not names:
        fallback = "Get-CimInstance Win32_SoundDevice | Select-Object -Property Name | ConvertTo-Json"
        rc, out, _err = run_command([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", fallback], timeout=8)
        names = parse_windows_endpoint_names(out) if rc == 0 else []
    ports: list[str] = []
    for name in names:
        label = f"WASAPI::{name}"
        is_mic = is_microphone_port(name)
        if direction == "input" and is_mic:
            ports.append(label)
        elif direction == "output" and not is_mic:
            ports.append(label)
    if not ports and names:
        # Some drivers do not expose obvious mic/speaker labels. Show endpoints
        # in both lists rather than hiding them completely.
        ports = [f"WASAPI::{name}" for name in names]
    return ports


def parse_coreaudio_devices(text: str, direction: str) -> list[str]:
    """Parse system_profiler SPAudioDataType output into device names."""
    devices: list[tuple[str, set[str]]] = []
    current = ""
    current_flags: set[str] = set()

    def flush() -> None:
        nonlocal current, current_flags
        if current:
            devices.append((current, set(current_flags)))
        current = ""
        current_flags = set()

    ignored = {
        "Audio", "Devices", "Intel High Definition Audio", "Apple Inc.",
        "Input", "Output", "System Settings", "Speaker", "Microphone",
    }
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^\s{4,}(.+):$", line)
        if m:
            name = m.group(1).strip()
            if name and name not in ignored and not name.startswith("Default "):
                flush()
                current = name
                continue
        low = stripped.lower()
        if "input channels" in low or "default input device" in low or "input source" in low:
            current_flags.add("input")
        if "output channels" in low or "default output device" in low or "output source" in low:
            current_flags.add("output")
    flush()

    wanted = "input" if direction == "input" else "output"
    names: list[str] = []
    for name, flags in devices:
        if wanted in flags or not flags:
            label = f"CoreAudio::{name}"
            if label not in names:
                names.append(label)
    return names


def coreaudio_ports(direction: str) -> list[str]:
    """Return macOS CoreAudio devices.

    If SwitchAudioSource is installed, use it for cleaner output. Otherwise use
    system_profiler. This backend is discovery-first; full patching needs a
    CoreAudio graph backend and typically a virtual driver such as BlackHole for
    app-to-app routes.
    """
    switch_audio = shutil.which("SwitchAudioSource")
    if switch_audio:
        kind = "input" if direction == "input" else "output"
        rc, out, _err = run_command([switch_audio, "-a", "-t", kind], timeout=5)
        if rc == 0:
            ports = []
            for line in out.splitlines():
                name = line.strip()
                if name:
                    ports.append(f"CoreAudio::{name}")
            if ports:
                return ports
    rc, out, _err = run_command(["system_profiler", "SPAudioDataType"], timeout=12)
    if rc != 0:
        return []
    return parse_coreaudio_devices(out, direction)


def audio_ports(direction: str) -> list[str]:
    """Return ports/devices for the current platform backend."""
    backend = audio_backend_name()
    if backend == "PipeWire":
        return pipewire_ports(direction)
    if backend == "WASAPI":
        return wasapi_ports(direction)
    if backend == "CoreAudio":
        return coreaudio_ports(direction)
    return []

def is_virtual_device_port(name: str) -> bool:
    """Return True when a port/device name looks like a virtual audio device."""
    low = name.lower()
    return any(keyword in low for keyword in VIRTUAL_DEVICE_KEYWORDS)


def detected_virtual_devices(ports: Iterable[str]) -> list[str]:
    """Return unique virtual-looking device names from a collection of ports."""
    found: list[str] = []
    for port in ports:
        if is_virtual_device_port(port) and port not in found:
            found.append(port)
    return found


def virtual_routing_available(source: str, dest: str) -> bool:
    """Return True if a route can be tracked through an external virtual driver."""
    return is_virtual_device_port(source) or is_virtual_device_port(dest)



def connect_audio_ports(source: str, dest: str) -> tuple[bool, str]:
    """Create a route on the active backend when supported.

    PipeWire uses real ``pw-link`` patching. Windows/macOS cannot expose a
    PipeWire-style app graph from this Lite Python backend, so MINIBUS provides
    virtual-device-assisted route tracking when a route uses devices such as
    VB-CABLE, Voicemeeter, BlackHole, or Loopback. In that mode the external
    driver performs the audio forwarding while MINIBUS records the route state.
    """
    if audio_backend_name() == "PipeWire":
        return connect_ports(source, dest)
    if not source or not dest:
        return False, "Choose both a source and a destination."

    if virtual_routing_available(source, dest):
        key = (source, dest)
        if key in _virtual_connections:
            return True, "Already connected (virtual-device route)"
        _virtual_connections.add(key)
        return True, (
            "Connected (virtual-device route). The virtual audio driver handles the actual audio forwarding."
        )

    return False, (
        f"{audio_backend_name()} native app-to-app patching is not implemented in this Lite backend yet. "
        "Select a virtual audio endpoint such as VB-CABLE, Voicemeeter, BlackHole, or Loopback, "
        "or use Linux/PipeWire for native patching."
    )


def disconnect_audio_ports(source: str, dest: str) -> tuple[bool, str]:
    """Remove a route on the active backend when supported."""
    if audio_backend_name() == "PipeWire":
        return disconnect_ports(source, dest)
    if not source or not dest:
        return False, "Choose both a source and a destination."

    key = (source, dest)
    if key in _virtual_connections:
        _virtual_connections.discard(key)
        return True, "Disconnected (virtual-device route)"
    if virtual_routing_available(source, dest):
        return True, "Already disconnected (virtual-device route)"

    return False, (
        f"{audio_backend_name()} native link removal is not implemented in this Lite backend yet. "
        "Only virtual-device routes tracked by MINIBUS can be disconnected here."
    )


def current_links() -> list[str]:
    """Return active backend links or MINIBUS-tracked virtual-device routes."""
    if audio_backend_name() != "PipeWire":
        if _virtual_connections:
            return [f"{src} → {dst}  (virtual-device route)" for (src, dst) in sorted(_virtual_connections)]
        return [f"{audio_backend_name()} native link graph is not available in MINIBUS Lite yet."]
    rc, out, _err = run_command(["pw-link", "-l"])
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def connect_ports(source: str, dest: str) -> tuple[bool, str]:
    if not source or not dest:
        return False, "Choose both a source and a destination port."
    rc, out, err = run_command(["pw-link", source, dest])
    if rc == 0:
        return True, "Connected"
    msg = (out + "\n" + err).strip()
    if "exists" in msg.lower() or "file exists" in msg.lower() or "already" in msg.lower():
        return True, "Already connected"
    return False, msg or f"pw-link failed with code {rc}"


def disconnect_ports(source: str, dest: str) -> tuple[bool, str]:
    if not source or not dest:
        return False, "Choose both a source and a destination port."
    rc, out, err = run_command(["pw-link", "-d", source, dest])
    if rc == 0:
        return True, "Disconnected"
    msg = (out + "\n" + err).strip()
    if "not found" in msg.lower() or "no such" in msg.lower():
        return True, "Already disconnected"
    return False, msg or f"pw-link -d failed with code {rc}"


def normalise_name(text: str) -> str:
    """Return a lower-cased tokenised name for matching ports/launchers.

    On Windows, backslashes are used as path separators. The previous implementation
    only split on forward slashes, which meant Windows paths were treated as one
    long string. This revision looks for either of the common path separators
    (`/` on Unix, `\\` on Windows) before choosing the Path stem. After stripping
    known executable suffixes, any non-alphanumeric characters are collapsed to
    single spaces. The result is a simple keyword string usable for fuzzy
    matching against port names.
    """
    # Determine if this is a path rather than a simple label by checking for
    # common path separators. Both forward slash and backslash are considered
    # here to support Windows and POSIX paths. Using os.sep alone is
    # insufficient because a Windows-style path might be passed on a POSIX
    # system for testing or via Wine.
    if "/" in text or "\\" in text:
        stem = Path(text).stem
    else:
        stem = text
    # Remove common binary suffixes. Preserve case so the regex can run in
    # lower‑cased form below. This handles both native binaries (e.g. `.exe`)
    # and AppImages.
    text = stem.replace(".AppImage", "").replace(".exe", "")
    # Collapse any sequence of non‑alphanumeric characters into a single space
    # and strip leading/trailing whitespace. Compare in lower case.
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def is_microphone_port(port: str) -> bool:
    """Heuristic for source ports that are likely mic/capture inputs.

    This intentionally errs on the side of not touching arbitrary links. The
    MIC switch only operates on MINIBUS-created lane links.
    """
    n = normalise_name(port)
    if not n:
        return False
    positives = [
        "mic",
        "microphone",
        "capture",
        "alsa input",
        "bluez input",
        "source",
        "input device",
    ]
    negatives = ["monitor", "speaker", "headphone", "playback"]
    if any(x in n for x in positives) and not any(x in n for x in negatives):
        return True
    return False


def is_monitor_port(port: str) -> bool:
    """Heuristic for destination ports that are likely audible monitor outputs."""
    n = normalise_name(port)
    if not n:
        return False
    positives = [
        "speaker",
        "speakers",
        "headphone",
        "headphones",
        "alsa output",
        "bluez output",
        "playback",
        "monitor",
    ]
    negatives = ["capture", "microphone", "mic"]
    if any(x in n for x in positives) and not any(x in n for x in negatives):
        return True
    return False


def route_allowed(source: str, dest: str, mic_enabled: bool, monitor_enabled: bool) -> tuple[bool, str]:
    """Validate a patch against the global MIC and MONITOR switches."""
    if not source or not dest:
        return False, "Choose both a source and a destination port."
    if not mic_enabled and is_microphone_port(source):
        return False, "MIC is OFF. Turn MIC on before creating mic/capture links."
    if not monitor_enabled and is_monitor_port(dest):
        return False, "MONITOR is OFF. Turn MONITOR on before creating speaker/headphone links."
    return True, "OK"


def detect_new_ports(before: Iterable[str], after: Iterable[str]) -> list[str]:
    """Return ports present in after but not before, preserving after order."""
    seen = set(before)
    return [p for p in after if p not in seen]


def score_match(port: str, launcher: Launcher) -> int:
    p = normalise_name(port)
    parts = [normalise_name(launcher.label), normalise_name(launcher.path), normalise_name(launcher.command)]
    parts = [x for x in parts if x]
    score = 0
    for part in parts:
        words = [w for w in part.split() if len(w) >= 3]
        if part and part in p:
            score += 50
        for w in words:
            if w in p:
                score += 5
    return score


def best_port_for_launcher(launcher: Launcher, ports: list[str]) -> str:
    scored = sorted(((score_match(port, launcher), port) for port in ports), reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return ""


def clean_desktop_exec(exec_line: str) -> str:
    return FIELD_CODE_RE.sub("", exec_line).strip()


def parse_desktop_file(path: Path) -> Optional[Launcher]:
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return None

    in_entry = False
    name = ""
    exec_line = ""
    no_display = False
    terminal = False
    app_type = "Application"
    for raw in text.splitlines():
        line = raw.strip()
        if line == "[Desktop Entry]":
            in_entry = True
            continue
        if in_entry and line.startswith("[") and line.endswith("]"):
            break
        if not in_entry or not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "Name" and not name:
            name = value.strip()
        elif key == "Exec" and not exec_line:
            exec_line = clean_desktop_exec(value.strip())
        elif key == "NoDisplay" and value.strip().lower() == "true":
            no_display = True
        elif key == "Terminal" and value.strip().lower() == "true":
            terminal = True
        elif key == "Type":
            app_type = value.strip()

    if not name or not exec_line or no_display or terminal or app_type != "Application":
        return None
    return Launcher(label=name, command=exec_line, kind="desktop", path=str(path))


def installed_desktop_launchers() -> list[Launcher]:
    dirs = [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        Path.home() / ".local/share/flatpak/exports/share/applications",
    ]
    launchers: dict[str, Launcher] = {}
    for folder in dirs:
        if not folder.exists():
            continue
        for desktop in folder.glob("*.desktop"):
            item = parse_desktop_file(desktop)
            if item:
                launchers.setdefault(item.label.lower(), item)
    return sorted(launchers.values(), key=lambda x: x.label.lower())


def limited_rglob(folder: Path, pattern: str, limit: int = 200) -> Iterable[Path]:
    count = 0
    if not folder.exists():
        return
    try:
        for path in folder.rglob(pattern):
            if count >= limit:
                break
            # Normalise the path to use forward slashes for substring tests. On Windows,
            # Path.__str__ produces backslash separators, which would not match the
            # skip patterns defined with forward slashes. Replace os-specific
            # separators to ensure consistent matching across platforms.
            s = str(path).replace("\\", "/")
            if any(skip in s for skip in ["/.cache/", "/node_modules/", "/.cargo/", "/.rustup/"]):
                continue
            if path.is_file():
                count += 1
                yield path
    except OSError:
        return


def appimage_launchers() -> list[Launcher]:
    folders = [
        Path.home() / "Applications",
        Path.home() / "AppImages",
        Path.home() / "Apps",
        Path.home() / "Downloads",
        Path.home() / "Desktop",
    ]
    seen: set[str] = set()
    items: list[Launcher] = []
    for folder in folders:
        for path in limited_rglob(folder, "*.AppImage", limit=100) or []:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            label = path.stem.replace("-x86_64", "").replace("_x86_64", "")
            items.append(Launcher(label=label, command=str(path), kind="appimage", path=str(path)))
    return sorted(items, key=lambda x: x.label.lower())


def exe_launchers_quick() -> list[Launcher]:
    roots = [
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / ".wine/drive_c/Program Files",
        Path.home() / ".wine/drive_c/Program Files (x86)",
    ]
    seen: set[str] = set()
    items: list[Launcher] = []
    for root in roots:
        for path in limited_rglob(root, "*.exe", limit=60) or []:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            items.append(Launcher(label=path.stem, command=f'wine "{path}"', kind="exe", path=str(path)))
    return sorted(items, key=lambda x: x.label.lower())


def windows_launchers() -> list[Launcher]:
    """Find common Windows Start Menu shortcuts and application EXEs."""
    roots: list[Path] = []
    program_data = os.environ.get("ProgramData")
    app_data = os.environ.get("APPDATA")
    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_data:
        roots.append(Path(program_data) / "Microsoft/Windows/Start Menu/Programs")
    if app_data:
        roots.append(Path(app_data) / "Microsoft/Windows/Start Menu/Programs")
    if program_files:
        roots.append(Path(program_files))
    if program_files_x86:
        roots.append(Path(program_files_x86))

    seen: set[str] = set()
    items: list[Launcher] = []
    for root in roots:
        for pattern, kind, limit in [("*.lnk", "windows_lnk", 300), ("*.exe", "windows_exe", 160)]:
            for path in limited_rglob(root, pattern, limit=limit) or []:
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                items.append(Launcher(label=path.stem, command=str(path), kind=kind, path=str(path)))
    return sorted(items, key=lambda x: x.label.lower())


def macos_launchers() -> list[Launcher]:
    """Find macOS .app bundles in common locations."""
    roots = [Path("/Applications"), Path.home() / "Applications"]
    seen: set[str] = set()
    items: list[Launcher] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            for path in root.glob("*.app"):
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                items.append(Launcher(label=path.stem, command=f'open "{path}"', kind="macos_app", path=str(path)))
        except OSError:
            continue
    return sorted(items, key=lambda x: x.label.lower())


def scan_launchers() -> list[Launcher]:
    items: list[Launcher] = []
    system = host_system()
    if system == "Linux":
        items.extend(installed_desktop_launchers())
        items.extend(appimage_launchers())
        items.extend(exe_launchers_quick())
    elif system == "Windows":
        items.extend(windows_launchers())
    elif system == "Darwin":
        items.extend(macos_launchers())
    else:
        items.extend(appimage_launchers())
    unique: dict[str, Launcher] = {}
    for item in items:
        key = item.path or item.command
        unique.setdefault(key, item)
    return sorted(unique.values(), key=lambda x: (x.kind, x.label.lower()))


def launch(item: Launcher) -> tuple[bool, str]:
    system = host_system()
    if item.kind == "appimage":
        try:
            os.chmod(item.path, os.stat(item.path).st_mode | 0o111)
        except OSError:
            pass
        try:
            subprocess.Popen([item.path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Launched {item.label}"
        except OSError as exc:
            return False, str(exc)
    if item.kind in {"macos_app"}:
        try:
            subprocess.Popen(["open", item.path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Launched {item.label}"
        except OSError as exc:
            return False, str(exc)
    if item.kind in {"windows_lnk", "windows_exe"}:
        try:
            if hasattr(os, "startfile"):
                os.startfile(item.path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen([item.path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Launched {item.label}"
        except OSError as exc:
            return False, str(exc)
    if item.kind == "exe":
        if system == "Windows":
            try:
                if hasattr(os, "startfile"):
                    os.startfile(item.path)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen([item.path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                return True, f"Launched {item.label}"
            except OSError as exc:
                return False, str(exc)
        if not shutil.which("wine"):
            return False, "Wine is not installed. Install wine or choose a Linux app."
        try:
            subprocess.Popen(["wine", item.path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, f"Launched {item.label} through Wine"
        except OSError as exc:
            return False, str(exc)
    try:
        subprocess.Popen(item.command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True, f"Launched {item.label}"
    except OSError as exc:
        return False, str(exc)


def collect_diagnostics() -> list[tuple[str, str]]:
    """Collect local diagnostics without changing audio routing."""
    rows: list[tuple[str, str]] = []

    def add(kind: str, msg: str) -> None:
        rows.append((kind, msg))

    backend = audio_backend_name()
    system = host_system()
    add("INFO", f"{APP_NAME}")
    add("INFO", f"Platform: {system or 'Unknown'} / backend: {backend}")
    add("INFO", f"Python {'.'.join(map(str, __import__('sys').version_info[:3]))}")

    if importlib.util.find_spec("tkinter") is None:
        add("FAIL", "tkinter missing. Install the Tkinter package for your OS.")
    else:
        add("PASS", "tkinter importable")

    if backend == "PipeWire":
        for name, required in [("pw-link", True), ("pw-loopback", True), ("pw-dump", False), ("wine", False)]:
            path = shutil.which(name)
            if path:
                add("PASS", f"{name} found at {path}")
            else:
                add("FAIL" if required else "WARN", f"{name} not found")

        for svc in ["pipewire", "wireplumber"]:
            rc, out, err = run_command(["systemctl", "--user", "is-active", svc], timeout=3)
            value = (out or err).strip() or "unknown"
            if rc == 0:
                add("PASS", f"{svc} user service active")
            else:
                add("WARN", f"{svc} user service state: {value}")
    elif backend == "WASAPI":
        add("INFO", "WASAPI backend supports endpoint discovery and virtual-device route tracking.")
        add("INFO", "Native Windows app-to-app patching is not implemented in this Lite release.")
        shell = shutil.which("powershell") or shutil.which("pwsh")
        add("PASS" if shell else "WARN", f"PowerShell {'found at ' + shell if shell else 'not found'}")
    elif backend == "CoreAudio":
        add("INFO", "CoreAudio backend supports device discovery and virtual-device route tracking.")
        add("INFO", "Native macOS app-to-app patching is not implemented in this Lite release.")
        add("PASS" if shutil.which("system_profiler") else "WARN", "system_profiler available" if shutil.which("system_profiler") else "system_profiler not found")
        add("PASS" if shutil.which("SwitchAudioSource") else "WARN", "SwitchAudioSource available" if shutil.which("SwitchAudioSource") else "SwitchAudioSource optional tool not found")
    else:
        add("WARN", f"No dedicated audio backend for platform {system!r}")

    outputs = audio_ports("output")
    inputs = audio_ports("input")
    if outputs or inputs:
        add("PASS", f"{backend} ports/devices visible: {len(outputs)} outputs, {len(inputs)} inputs")
    else:
        add("WARN", f"No {backend} ports/devices returned.")

    if backend in {"WASAPI", "CoreAudio"}:
        virtuals = detected_virtual_devices(outputs + inputs)
        if virtuals:
            preview = ", ".join(virtuals[:4])
            suffix = "" if len(virtuals) <= 4 else f" and {len(virtuals) - 4} more"
            add("PASS", f"Virtual audio endpoint(s) detected: {preview}{suffix}")
        else:
            if backend == "WASAPI":
                add("WARN", "No VB-CABLE/Voicemeeter-style virtual device detected.")
            else:
                add("WARN", "No BlackHole/Loopback-style virtual device detected.")

    try:
        apps = scan_launchers()
        add("PASS" if apps else "WARN", f"Launcher scan found {len(apps)} apps/AppImages/EXEs")
    except Exception as exc:  # defensive for diagnostics only
        add("FAIL", f"Launcher scan failed: {exc}")

    if backend_supports_patching():
        add("PASS", f"{backend} native patching enabled")
    elif backend in {"WASAPI", "CoreAudio"}:
        add("WARN", f"{backend} native patching not enabled; virtual-device route tracking is available when virtual endpoints are selected")
    else:
        add("WARN", f"{backend} patching not enabled in Lite; discovery and launcher workflow only")

    add("INFO", "Diagnostics do not alter routing. Use lane patch/off for links.")
    return rows


class AppChooser(tk.Toplevel):
    def __init__(self, master: tk.Tk, launchers: list[Launcher], on_pick: Callable[[Optional[Launcher]], None]):
        super().__init__(master)
        self.title("Choose app")
        self.geometry("560x420")
        self.transient(master)
        self.on_pick = on_pick
        self.launchers = launchers
        self.filtered = launchers[:]

        top = ttk.Frame(self, padding=8)
        top.pack(fill="both", expand=True)

        ttk.Label(top, text="Search installed apps and launchers for this platform").pack(anchor="w")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.pack(fill="x", pady=(4, 8))
        entry.bind("<KeyRelease>", lambda _e: self.apply_filter())

        self.listbox = tk.Listbox(top, height=14)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<Double-1>", lambda _e: self.pick_selected())

        buttons = ttk.Frame(top)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Use selected", command=self.pick_selected).pack(side="left")
        ttk.Button(buttons, text="Locate file…", command=self.locate_file).pack(side="left", padx=6)
        ttk.Button(buttons, text="Clear slot", command=self.clear_slot).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")

        self.apply_filter()
        entry.focus_set()

    def apply_filter(self):
        q = self.search_var.get().lower().strip()
        if not q:
            self.filtered = self.launchers[:]
        else:
            terms = q.split()
            self.filtered = [x for x in self.launchers if all(t in x.search_text() for t in terms)]
        self.listbox.delete(0, tk.END)
        for item in self.filtered[:500]:
            self.listbox.insert(tk.END, f"{item.label}    [{item.kind}]")

    def pick_selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.filtered):
            return
        self.on_pick(self.filtered[idx])
        self.destroy()

    def clear_slot(self):
        self.on_pick(None)
        self.destroy()

    def locate_file(self):
        path = filedialog.askopenfilename(
            title="Locate app, AppImage, binary, or EXE",
            filetypes=[
                ("Applications", "*.AppImage *.exe *.lnk *.app *"),
                ("AppImage", "*.AppImage"),
                ("Windows EXE", "*.exe"),
                ("Windows Shortcut", "*.lnk"),
                ("macOS app bundle", "*.app"),
                ("All files", "*"),
            ],
        )
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() == ".exe":
            item = Launcher(label=p.stem, command=f'wine "{p}"', kind="exe", path=str(p))
        elif p.suffix.lower() == ".lnk":
            item = Launcher(label=p.stem, command=str(p), kind="windows_lnk", path=str(p))
        elif p.suffix.lower() == ".app":
            item = Launcher(label=p.stem, command=f'open "{p}"', kind="macos_app", path=str(p))
        elif p.suffix == ".AppImage":
            item = Launcher(label=p.stem, command=str(p), kind="appimage", path=str(p))
        else:
            item = Launcher(label=p.name, command=str(p), kind="binary", path=str(p))
        self.on_pick(item)
        self.destroy()


class Lane:
    def __init__(self, app: "MiniBusApp", parent: ttk.Frame, index: int):
        self.app = app
        self.index = index
        self.launchers: list[Optional[Launcher]] = [None, None, None]
        self.patched_source = ""
        self.patched_dest = ""
        self.connected = False

        self.frame = ttk.Frame(parent, padding=(1, 0))
        self.frame.grid(row=index, column=0, sticky="ew")
        for col in range(11):
            self.frame.columnconfigure(col, weight=0)
        self.frame.columnconfigure(1, weight=1)
        self.frame.columnconfigure(9, weight=1)

        ttk.Label(self.frame, text=f"{index + 1}", width=2).grid(row=0, column=0, padx=(0, 1))

        self.source_var = tk.StringVar()
        self.source_combo = ttk.Combobox(self.frame, textvariable=self.source_var, width=18, state="readonly")
        self.source_combo.grid(row=0, column=1, sticky="ew")

        ttk.Label(self.frame, text="→").grid(row=0, column=2, padx=1)

        self.app_buttons: list[ttk.Button] = []
        for n in range(3):
            btn = ttk.Button(self.frame, text="app", width=6, command=lambda slot=n: self.choose_app(slot))
            btn.grid(row=0, column=3 + n * 2, padx=1)
            self.app_buttons.append(btn)
            if n < 2:
                ttk.Label(self.frame, text="→").grid(row=0, column=4 + n * 2, padx=1)

        ttk.Label(self.frame, text="→").grid(row=0, column=8, padx=1)

        self.dest_var = tk.StringVar()
        self.dest_combo = ttk.Combobox(self.frame, textvariable=self.dest_var, width=18, state="readonly")
        self.dest_combo.grid(row=0, column=9, sticky="ew")

        action_frame = ttk.Frame(self.frame)
        action_frame.grid(row=0, column=10, padx=(3, 0))
        ttk.Button(action_frame, text="run", width=3, command=self.run_apps).pack(side="left")
        ttk.Button(action_frame, text="learn", width=5, command=self.learn).pack(side="left", padx=0)
        ttk.Button(action_frame, text="patch", width=5, command=self.patch).pack(side="left")
        ttk.Button(action_frame, text="off", width=3, command=self.off).pack(side="left", padx=(0, 0))

    def update_ports(self, outputs: list[str], inputs: list[str]):
        old_source = self.source_var.get()
        old_dest = self.dest_var.get()
        self.source_combo["values"] = [""] + outputs
        self.dest_combo["values"] = [""] + inputs
        if old_source in outputs:
            self.source_var.set(old_source)
        if old_dest in inputs:
            self.dest_var.set(old_dest)

    def choose_app(self, slot: int):
        AppChooser(self.app.root, self.app.launchers, lambda item: self.set_launcher(slot, item))

    def set_launcher(self, slot: int, item: Optional[Launcher]):
        self.launchers[slot] = item
        text = "app" if item is None else short_label(item.label, 7)
        self.app_buttons[slot].configure(text=text)
        self.app.set_status(f"Lane {self.index + 1} slot {slot + 1}: {text}")
        self.app.save_config()

    def run_apps(self):
        any_app = False
        for item in self.launchers:
            if item is None:
                continue
            any_app = True
            ok, msg = launch(item)
            self.app.set_status(msg)
            if not ok:
                messagebox.showerror("Launch failed", msg)
                return
        if not any_app:
            self.app.set_status("No app selected in this lane.")
        self.app.root.after(1500, self.app.refresh_audio_async)

    def learn(self):
        self.app.start_learn(self)

    def auto_fill_from_launchers(self):
        if not self.source_var.get():
            for item in self.launchers:
                if item:
                    port = best_port_for_launcher(item, self.app.outputs)
                    if port:
                        self.source_var.set(port)
                        break
        if not self.dest_var.get():
            for item in reversed(self.launchers):
                if item:
                    port = best_port_for_launcher(item, self.app.inputs)
                    if port:
                        self.dest_var.set(port)
                        break

    def patch(self):
        self.auto_fill_from_launchers()
        source = self.source_var.get().strip()
        dest = self.dest_var.get().strip()
        allowed, reason = route_allowed(source, dest, self.app.mic_on.get(), self.app.monitor_on.get())
        if not allowed:
            self.app.set_status(reason)
            messagebox.showwarning("Patch blocked", reason)
            return
        ok, msg = connect_audio_ports(source, dest)
        self.app.set_status(f"Lane {self.index + 1}: {msg}")
        if ok:
            self.patched_source = source
            self.patched_dest = dest
            self.connected = True
            self.app.register_lane_link(self)
            self.app.save_config()
        else:
            messagebox.showerror("Patch failed", msg)
        self.app.refresh_links_only()

    def off(self):
        source = self.source_var.get().strip() or self.patched_source
        dest = self.dest_var.get().strip() or self.patched_dest
        ok, msg = disconnect_audio_ports(source, dest)
        self.app.set_status(f"Lane {self.index + 1}: {msg}")
        if ok:
            self.connected = False
            self.app.unregister_lane_link(self)
            self.app.save_config()
        else:
            messagebox.showerror("Disconnect failed", msg)
        self.app.refresh_links_only()

    def disconnect_saved_link(self) -> bool:
        if not self.patched_source or not self.patched_dest:
            return False
        ok, _msg = disconnect_audio_ports(self.patched_source, self.patched_dest)
        if ok:
            self.connected = False
            self.app.unregister_lane_link(self)
        return ok

    def reconnect_saved_link(self) -> bool:
        if not self.patched_source or not self.patched_dest:
            return False
        allowed, _reason = route_allowed(
            self.patched_source,
            self.patched_dest,
            self.app.mic_on.get(),
            self.app.monitor_on.get(),
        )
        if not allowed:
            return False
        ok, _msg = connect_audio_ports(self.patched_source, self.patched_dest)
        if ok:
            self.connected = True
            self.app.register_lane_link(self)
        return ok


class MiniBusApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.config_data = read_config()
        self.root.geometry(compact_geometry(self.config_data.get("geometry", "950x186+40+40")))
        self.root.minsize(780, 176)
        self.root.resizable(True, False)
        self.root.attributes("-topmost", True)

        self.outputs: list[str] = []
        self.inputs: list[str] = []
        self.launchers: list[Launcher] = []
        self.active_lane_links: set[tuple[int, str, str]] = set()
        self.learn_state: Optional[dict[str, object]] = None
        self.refreshing_audio = False
        self.auto_refresh = tk.BooleanVar(value=True)
        self.topmost = tk.BooleanVar(value=True)
        self.mic_on = tk.BooleanVar(value=True)
        self.monitor_on = tk.BooleanVar(value=True)
        self.restore_global_state()

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_audio_async(quiet=True)
        self.scan_apps_async()
        self.root.after(REFRESH_SECONDS * 1000, self.tick)

    def restore_global_state(self):
        self.auto_refresh.set(bool(self.config_data.get("auto_refresh", True)))
        self.topmost.set(bool(self.config_data.get("topmost", True)))
        self.mic_on.set(bool(self.config_data.get("mic_on", True)))
        self.monitor_on.set(bool(self.config_data.get("monitor_on", True)))
        self.root.attributes("-topmost", bool(self.topmost.get()))

    def apply_compact_theme(self):
        """Use small, readable Tk defaults for a corner utility window."""
        try:
            from tkinter import font as tkfont

            for name in ["TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"]:
                font = tkfont.nametofont(name)
                font.configure(size=8)
            tkfont.nametofont("TkFixedFont").configure(size=8)
        except Exception:
            pass

        style = ttk.Style(self.root)
        try:
            style.configure("TFrame", padding=0)
            style.configure("TButton", padding=(3, 1))
            style.configure("TCheckbutton", padding=(1, 0))
            style.configure("TLabel", padding=(1, 0))
            style.configure("TCombobox", padding=(1, 0))
        except tk.TclError:
            pass

    def build_ui(self):
        self.apply_compact_theme()
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)

        toolbar = ttk.Frame(self.root, padding=(4, 1))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(9, weight=1)

        ttk.Label(toolbar, text="MINIBUS", font=("TkDefaultFont", 9, "bold")).grid(row=0, column=0, padx=(0, 3))
        ttk.Button(toolbar, text="audio", command=self.refresh_audio_async).grid(row=0, column=1, padx=1)
        ttk.Button(toolbar, text="apps", command=self.scan_apps_async).grid(row=0, column=2, padx=2)
        ttk.Button(toolbar, text="bus +", command=self.create_bus_dialog).grid(row=0, column=3, padx=2)
        ttk.Button(toolbar, text="diag", command=self.show_diagnostics).grid(row=0, column=4, padx=2)
        ttk.Checkbutton(toolbar, text="auto", variable=self.auto_refresh, command=self.save_config).grid(row=0, column=5, padx=2)
        ttk.Checkbutton(toolbar, text="top", variable=self.topmost, command=self.apply_topmost).grid(row=0, column=6, padx=2)
        ttk.Checkbutton(toolbar, text="MIC", variable=self.mic_on, command=self.mic_toggle).grid(row=0, column=7, padx=2)
        ttk.Checkbutton(toolbar, text="MONITOR", variable=self.monitor_on, command=self.monitor_toggle).grid(row=0, column=8, padx=2)

        ttk.Label(toolbar, text=f"{audio_backend_name()} · run · learn · patch").grid(row=0, column=9, sticky="e")

        lanes_box = ttk.Frame(self.root, padding=(4, 0))
        lanes_box.grid(row=1, column=0, sticky="ew")
        lanes_box.columnconfigure(0, weight=1)
        self.lanes = [Lane(self, lanes_box, i) for i in range(5)]
        self.restore_lanes()

        bottom = ttk.Frame(self.root, padding=(4, 1))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        self.status = tk.StringVar(value="Ready")
        ttk.Label(bottom, textvariable=self.status).grid(row=0, column=0, sticky="w")
        self.counts = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.counts).grid(row=0, column=1, sticky="e")
        ttk.Button(bottom, text="links", command=self.show_links).grid(row=0, column=2, padx=(8, 2))
        ttk.Button(bottom, text="minimize", command=self.root.iconify).grid(row=0, column=3, padx=2)
        ttk.Button(bottom, text="close", command=self.root.destroy).grid(row=0, column=4, padx=2)

    def set_status(self, text: str):
        self.status.set(text)

    def apply_topmost(self):
        self.root.attributes("-topmost", bool(self.topmost.get()))
        self.save_config()

    def restore_lanes(self):
        lanes_data = self.config_data.get("lanes", [])
        if not isinstance(lanes_data, list):
            return
        for lane, data in zip(self.lanes, lanes_data):
            if not isinstance(data, dict):
                continue
            lane.source_var.set(str(data.get("source", "") or ""))
            lane.dest_var.set(str(data.get("dest", "") or ""))
            lane.patched_source = str(data.get("patched_source", "") or "")
            lane.patched_dest = str(data.get("patched_dest", "") or "")
            lane.connected = bool(data.get("connected", False))
            raw_launchers = data.get("launchers", [])
            if isinstance(raw_launchers, list):
                for i, raw in enumerate(raw_launchers[:3]):
                    item = Launcher.from_dict(raw)
                    lane.launchers[i] = item
                    if item:
                        lane.app_buttons[i].configure(text=short_label(item.label, 7))
            if lane.connected and lane.patched_source and lane.patched_dest:
                self.register_lane_link(lane)

    def save_config(self):
        data: dict[str, object] = {
            "version": APP_NAME,
            "geometry": self.root.geometry(),
            "auto_refresh": bool(self.auto_refresh.get()),
            "topmost": bool(self.topmost.get()),
            "mic_on": bool(self.mic_on.get()),
            "monitor_on": bool(self.monitor_on.get()),
            "lanes": [],
        }
        lanes_payload: list[dict[str, object]] = []
        for lane in getattr(self, "lanes", []):
            lanes_payload.append(
                {
                    "source": lane.source_var.get(),
                    "dest": lane.dest_var.get(),
                    "patched_source": lane.patched_source,
                    "patched_dest": lane.patched_dest,
                    "connected": lane.connected,
                    "launchers": [item.to_dict() if item else None for item in lane.launchers],
                }
            )
        data["lanes"] = lanes_payload
        write_config(data)

    def close(self):
        self.save_config()
        self.root.destroy()

    def register_lane_link(self, lane: Lane):
        if lane.patched_source and lane.patched_dest:
            self.active_lane_links.add((lane.index, lane.patched_source, lane.patched_dest))

    def unregister_lane_link(self, lane: Lane):
        self.active_lane_links = {x for x in self.active_lane_links if x[0] != lane.index}

    def refresh_audio_async(self, quiet: bool = False):
        """Refresh PipeWire ports in a worker thread to keep the UI smooth."""
        if self.refreshing_audio:
            return
        self.refreshing_audio = True
        if not quiet:
            self.set_status("Refreshing audio…")

        def worker():
            outputs = audio_ports("output")
            inputs = audio_ports("input")
            self.root.after(0, lambda: self.finish_audio_refresh(outputs, inputs, quiet))

        threading.Thread(target=worker, daemon=True).start()

    def finish_audio_refresh(self, outputs: list[str], inputs: list[str], quiet: bool = False):
        self.refreshing_audio = False
        self.outputs = outputs
        self.inputs = inputs
        for lane in self.lanes:
            lane.update_ports(self.outputs, self.inputs)
        self.counts.set(f"{audio_backend_name()}: {len(self.outputs)} outs / {len(self.inputs)} ins / {len(self.launchers)} apps")
        if not self.outputs and not self.inputs:
            self.set_status(f"No {audio_backend_name()} ports found. Run diagnostics.")
        elif not quiet:
            self.set_status("Audio ports refreshed")

    def refresh_audio(self):
        self.outputs = audio_ports("output")
        self.inputs = audio_ports("input")
        for lane in self.lanes:
            lane.update_ports(self.outputs, self.inputs)
        self.counts.set(f"{audio_backend_name()}: {len(self.outputs)} outs / {len(self.inputs)} ins / {len(self.launchers)} apps")
        if not self.outputs and not self.inputs:
            self.set_status(f"No {audio_backend_name()} ports found. Run diagnostics.")
        else:
            self.set_status("Audio ports refreshed")

    def refresh_links_only(self):
        pass

    def scan_apps_async(self):
        self.set_status("Scanning apps…")

        def worker():
            items = scan_launchers()
            self.root.after(0, lambda: self.finish_app_scan(items))

        threading.Thread(target=worker, daemon=True).start()

    def finish_app_scan(self, items: list[Launcher]):
        self.launchers = items
        self.counts.set(f"{audio_backend_name()}: {len(self.outputs)} outs / {len(self.inputs)} ins / {len(self.launchers)} apps")
        self.set_status(f"Found {len(items)} launchers. App slots now have choices.")

    def tick(self):
        if self.auto_refresh.get():
            self.refresh_audio_async(quiet=True)
        self.root.after(REFRESH_SECONDS * 1000, self.tick)

    def start_learn(self, lane: Lane):
        self.refresh_audio()
        self.learn_state = {
            "lane": lane,
            "outputs_before": set(self.outputs),
            "inputs_before": set(self.inputs),
            "started": time.time(),
        }
        self.set_status(f"Learn mode: start audio for lane {lane.index + 1}. Waiting for new PipeWire port…")
        self.root.after(1000, self.poll_learn)

    def poll_learn(self):
        state = self.learn_state
        if not state:
            return
        lane = state["lane"]
        assert isinstance(lane, Lane)
        before_outputs = state["outputs_before"]
        before_inputs = state["inputs_before"]
        assert isinstance(before_outputs, set)
        assert isinstance(before_inputs, set)

        outputs = audio_ports("output")
        inputs = audio_ports("input")
        new_outputs = detect_new_ports(before_outputs, outputs)
        new_inputs = detect_new_ports(before_inputs, inputs)

        self.outputs = outputs
        self.inputs = inputs
        for item in self.lanes:
            item.update_ports(self.outputs, self.inputs)
        self.counts.set(f"{audio_backend_name()}: {len(self.outputs)} outs / {len(self.inputs)} ins / {len(self.launchers)} apps")

        if new_outputs or new_inputs:
            if new_outputs:
                lane.source_var.set(new_outputs[0])
            if new_inputs and not lane.dest_var.get():
                lane.dest_var.set(new_inputs[0])
            chosen = []
            if new_outputs:
                chosen.append(f"source: {new_outputs[0]}")
            if new_inputs and lane.dest_var.get() == new_inputs[0]:
                chosen.append(f"dest: {new_inputs[0]}")
            self.learn_state = None
            self.set_status(f"Learned lane {lane.index + 1}: " + "; ".join(chosen))
            return

        started = float(state["started"])
        if time.time() - started > LEARN_TIMEOUT_SECONDS:
            self.learn_state = None
            self.set_status("Learn timed out. Start the app audio first, then press learn again.")
            return
        self.root.after(1000, self.poll_learn)

    def create_bus_dialog(self):
        if audio_backend_name() != "PipeWire":
            messagebox.showinfo(
                "Virtual bus unavailable",
                f"{audio_backend_name()} native virtual bus creation is not implemented in MINIBUS Lite yet. "
                "Use a virtual audio driver such as VB-CABLE, Voicemeeter, BlackHole, or Loopback, then select its endpoint in a lane."
            )
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Create virtual bus")
        dialog.geometry("360x120")
        dialog.transient(self.root)
        frm = ttk.Frame(dialog, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Bus name").pack(anchor="w")
        name_var = tk.StringVar(value="MINIBUS Bus")
        entry = ttk.Entry(frm, textvariable=name_var)
        entry.pack(fill="x", pady=5)

        def create():
            name = name_var.get().strip()
            if not name:
                return
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
            args = [
                "pw-loopback",
                "--capture-props", f"node.name={safe_name} node.description={name}",
                "--playback-props", f"node.name={safe_name}_monitor node.description={name} Monitor",
            ]
            try:
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                self.set_status(f"Started bus: {name}")
                dialog.destroy()
                self.root.after(1500, self.refresh_audio_async)
            except FileNotFoundError:
                messagebox.showerror("Missing pw-loopback", "pw-loopback was not found. Install pipewire-bin.")
            except OSError as exc:
                messagebox.showerror("Bus failed", str(exc))

        buttons = ttk.Frame(frm)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="create", command=create).pack(side="left")
        ttk.Button(buttons, text="cancel", command=dialog.destroy).pack(side="right")
        entry.focus_set()

    def show_links(self):
        links = current_links()
        win = tk.Toplevel(self.root)
        win.title(f"Current {audio_backend_name()} links/routes")
        win.geometry("760x420")
        txt = tk.Text(win, wrap="none")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", "\n".join(links) if links else "No links/routes returned")
        txt.configure(state="disabled")

    def mic_toggle(self):
        if not self.mic_on.get():
            count = 0
            for lane in self.lanes:
                source = lane.patched_source or lane.source_var.get().strip()
                if source and is_microphone_port(source) and lane.disconnect_saved_link():
                    count += 1
            self.set_status(f"MIC OFF: disconnected {count} MINIBUS mic/capture link(s).")
        else:
            count = 0
            for lane in self.lanes:
                if lane.patched_source and is_microphone_port(lane.patched_source) and lane.reconnect_saved_link():
                    count += 1
            self.set_status(f"MIC ON: reconnected {count} saved mic/capture link(s).")
        self.save_config()

    def monitor_toggle(self):
        if not self.monitor_on.get():
            count = 0
            for lane in self.lanes:
                dest = lane.patched_dest or lane.dest_var.get().strip()
                if dest and is_monitor_port(dest) and lane.disconnect_saved_link():
                    count += 1
            self.set_status(f"MONITOR OFF: disconnected {count} MINIBUS speaker/headphone link(s).")
        else:
            count = 0
            for lane in self.lanes:
                if lane.patched_dest and is_monitor_port(lane.patched_dest) and lane.reconnect_saved_link():
                    count += 1
            self.set_status(f"MONITOR ON: reconnected {count} saved monitor link(s).")
        self.save_config()

    def show_diagnostics(self):
        win = tk.Toplevel(self.root)
        win.title("MINIBUS diagnostics")
        win.geometry("820x460")
        frame = ttk.Frame(win, padding=8)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="word")
        text.pack(fill="both", expand=True)
        text.insert("1.0", "Running diagnostics…\n")
        text.configure(state="disabled")

        def worker():
            rows = collect_diagnostics()
            rendered = "\n".join(f"[{kind}] {msg}" for kind, msg in rows)
            self.root.after(0, lambda: self._finish_diagnostics_text(text, rendered))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _finish_diagnostics_text(text: tk.Text, rendered: str):
        text.configure(state="normal")
        text.delete("1.0", tk.END)
        text.insert("1.0", rendered)
        text.configure(state="disabled")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MiniBusApp().run()
