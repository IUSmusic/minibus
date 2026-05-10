#!/usr/bin/env python3
"""
MINIBUS Lite v0.4.1 diagnostic runner.

Run this from inside the project folder:

    python3 diagnose_minibus.py

Optional live bus test:

    python3 diagnose_minibus.py --bus-test

The normal diagnostic does not create or destroy audio links. The bus test
briefly starts pw-loopback, checks that PipeWire can see it, then terminates it.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import io
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def status(kind: str, msg: str) -> None:
    print(f"[{kind}] {msg}")


def run(args: list[str], timeout: float = 5.0) -> tuple[int, str, str]:
    try:
        p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except PermissionError as exc:
        return 126, "", str(exc)
    except OSError as exc:
        return 126, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "timed out"


def check_import_and_core_tests() -> None:
    """Run the bundled unit tests in-process for reliable diagnostics."""
    stream = io.StringIO()
    try:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        if result.wasSuccessful():
            status("PASS", "Core unit tests passed")
        else:
            status("FAIL", "Core unit tests failed")
        print(stream.getvalue())
    except Exception as exc:
        status("FAIL", f"Core unit tests could not run: {exc}")


def live_bus_test() -> None:
    import minibus
    if minibus.audio_backend_name() != "PipeWire":
        status("WARN", f"--bus-test is only available on the PipeWire backend. Current backend: {minibus.audio_backend_name()}")
        return
    name = f"MINIBUS_TEST_{os.getpid()}"
    if not shutil.which("pw-loopback"):
        status("FAIL", "pw-loopback missing; cannot run live bus test")
        return
    args = [
        "pw-loopback",
        "--capture-props", f"node.name={name} node.description={name}",
        "--playback-props", f"node.name={name}_monitor node.description={name} Monitor",
    ]
    status("INFO", f"Starting temporary bus {name}")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2.0)
        rc_o, out_o, _ = run(["pw-link", "-o"], timeout=4)
        rc_i, out_i, _ = run(["pw-link", "-i"], timeout=4)
        found = name in (out_o + out_i)
        if found:
            status("PASS", "Temporary pw-loopback bus appeared in PipeWire")
        else:
            status("WARN", "Temporary bus did not appear. PipeWire/WirePlumber policy may differ.")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        status("INFO", "Temporary bus stopped")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bus-test", action="store_true", help="briefly create a temporary pw-loopback bus")
    args = parser.parse_args()

    print("MINIBUS Lite v0.4.1 diagnostic")
    print(f"Project: {ROOT}")
    print(f"Python:  {sys.version.split()[0]}")
    print()

    import minibus

    for kind, msg in minibus.collect_diagnostics():
        status(kind, msg)
    print()
    check_import_and_core_tests()
    if args.bus_test:
        live_bus_test()

    print()
    status("INFO", "Diagnostic complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
