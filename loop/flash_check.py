"""Compile a sketch, upload it to the Nano 33 BLE, and wait for its READY line.

Usage: python loop/flash_check.py firmware/blink [--timeout 10]
Set ARDUINO_CLI to the arduino-cli executable if it is not on PATH.
"""
import argparse
import os
import subprocess
import sys
import time

import serial
from serial.tools import list_ports

FQBN = "arduino:mbed_nano:nano33ble"
CLI = os.environ.get("ARDUINO_CLI", "arduino-cli")
VID = 0x2341
APP_PID = 0x805A   # the sketch's own USB serial port
BOOT_PID = 0x005A  # the bootloader's port, a different device with its own COM number


def ports(pid):
    return [p.device for p in list_ports.comports() if p.vid == VID and p.pid == pid]


def wait_for(pid, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = ports(pid)
        if found:
            return found[0]
        time.sleep(0.1)
    return None


def enter_bootloader(timeout):
    """Return the bootloader port, touching the sketch port at 1200 baud if needed.

    arduino-cli's own touch decides which port is new from the SERIALCOMM registry
    list, which on this machine keeps a stale entry for the bootloader's COM number
    while the board is in sketch mode. The new port then never looks new, the wait
    runs out and bossac is pointed at the sketch port. Matching the bootloader by
    USB PID avoids the registry list entirely.
    """
    boot = ports(BOOT_PID)
    if boot:
        return boot[0]
    app = ports(APP_PID)
    if not app:
        return None
    serial.Serial(app[0], 1200).close()
    return wait_for(BOOT_PID, timeout)


def run_with_timeout(cmd, timeout):
    """Return the exit code, or None after killing the whole process tree on timeout."""
    proc = subprocess.Popen(cmd)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # bossac is a grandchild and outlives a plain kill; a leftover one grabs
        # the bootloader port on the next upload, so the whole tree has to go.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.wait()
        return None


def open_board(port):
    """Open the sketch port so that nothing the board sends on connect is lost.

    The sketch speaks once it sees DTR. pyserial on Windows raises DTR while
    configuring the port and only then purges the receive buffer
    (serialwin32.py open(): _reconfigure_port, then PurgeComm), so a line sent
    on connect can be wiped. Raising DTR after open puts it after the purge.
    """
    ser = serial.Serial(baudrate=115200, timeout=0.5)
    ser.port = port
    ser.dtr = False
    ser.open()
    ser.dtr = True
    return ser


def read_ready(port, timeout):
    deadline = time.monotonic() + timeout
    with open_board(port) as ser:
        while time.monotonic() < deadline:
            line = ser.readline().decode("utf-8", "replace").strip()
            if line.startswith("READY"):
                return line
    return None


class FlashError(Exception):
    pass


def flash(sketch, timeout=10, upload_timeout=180):
    """Compile and upload; return (sketch port, bootloader port, compile s, upload s)."""
    t0 = time.monotonic()
    code = run_with_timeout([CLI, "compile", "--fqbn", FQBN, sketch], upload_timeout)
    if code != 0:
        raise FlashError("compile timed out" if code is None else f"compile exited {code}")
    t_compile = time.monotonic() - t0

    boot = enter_bootloader(timeout)
    if not boot:
        raise FlashError("no Nano 33 BLE found, or it did not enter the bootloader")

    t1 = time.monotonic()
    code = run_with_timeout([CLI, "upload", "--fqbn", FQBN, "--port", boot,
                             "--upload-property", "upload.use_1200bps_touch=false",
                             "--upload-property", "upload.wait_for_upload_port=false",
                             sketch], upload_timeout)
    if code != 0:
        raise FlashError(f"upload on {boot} " + ("timed out, killed" if code is None else f"exited {code}"))
    t_upload = time.monotonic() - t1

    app = wait_for(APP_PID, timeout)
    if not app:
        raise FlashError("board did not come back after upload")
    return app, boot, t_compile, t_upload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sketch")
    ap.add_argument("--timeout", type=float, default=10)
    ap.add_argument("--upload-timeout", type=float, default=180)
    args = ap.parse_args()

    t0 = time.monotonic()
    try:
        app, boot, t_compile, t_upload = flash(args.sketch, args.timeout, args.upload_timeout)
    except FlashError as e:
        sys.exit(f"FAIL: {e}")
    line = read_ready(app, args.timeout)
    if not line:
        sys.exit(f"FAIL: no READY line on {app} within {args.timeout}s")
    print(f"PASS: {line} on {app} via {boot} "
          f"(compile {t_compile:.1f}s, upload {t_upload:.1f}s, total {time.monotonic() - t0:.1f}s)")


if __name__ == "__main__":
    main()
