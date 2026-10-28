"""Launcher helper: kill whatever process is listening on a TCP port.

Standard library only. Uses `netstat -ano` to find LISTENING owners, then
`taskkill /F /PID`. Never kills this helper itself, PID 0, or PID 4.
Any failure exits 0: the launcher already tells the user to close stray
windows, so this is best-effort cleanup, not a hard gate.
"""

import os
import re
import subprocess
import sys


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    try:
        proc = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True,
            timeout=15)
    except Exception:
        return 0
    if proc.returncode != 0:
        return 0
    me = os.getpid()
    pids = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0].upper() != "TCP":
            continue
        local, state, pid = parts[1], parts[-2], parts[-1]
        if state.upper() != "LISTENING" or not pid.isdigit():
            continue
        host_port = local.rsplit(":", 1)
        if len(host_port) != 2 or host_port[1] != port:
            continue
        if int(pid) not in (0, 4, me):
            pids.add(pid)
    for pid in sorted(pids):
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", pid],
                capture_output=True, timeout=15)
        except Exception:
            continue
    return 0


if __name__ == "__main__":
    sys.exit(main())
