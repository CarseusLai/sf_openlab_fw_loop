"""Print every line the Nano 33 BLE sends for a while, stamped with host time.

Usage: python loop/serial_log.py --seconds 30 [--out run.log]
"""
import argparse
import sys
import time

from flash_check import APP_PID, open_board, wait_for


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--out")
    args = ap.parse_args()

    port = wait_for(APP_PID, 10)
    if not port:
        sys.exit("FAIL: no Nano 33 BLE running a sketch")
    out = open(args.out, "w", encoding="utf-8") if args.out else None
    t0 = time.monotonic()
    with open_board(port) as ser:
        while time.monotonic() - t0 < args.seconds:
            line = ser.readline().decode("utf-8", "replace").strip()
            if line:
                stamped = f"{time.monotonic() - t0:6.2f} {line}"
                print(stamped, flush=True)
                if out:
                    out.write(stamped + "\n")
    if out:
        out.close()


if __name__ == "__main__":
    main()
