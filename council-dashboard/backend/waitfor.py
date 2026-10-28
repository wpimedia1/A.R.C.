"""Launcher helper: wait for an HTTP endpoint. Standard library only."""

import sys
import time
import urllib.request

url = sys.argv[1]
tries = int(sys.argv[2])
delay = float(sys.argv[3])

for _ in range(tries):
    try:
        if urllib.request.urlopen(url, timeout=5).status == 200:
            print("up")
            sys.exit(0)
    except Exception:
        pass
    time.sleep(delay)

print("down")
sys.exit(1)
