"""Launcher helper: wait for an HTTP endpoint; print the failure body. Standard library only."""
import sys
import time
import urllib.error
import urllib.request

url, tries, delay = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
last = 'no response'
for _ in range(tries):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            if r.status == 200:
                print('up')
                sys.exit(0)
    except urllib.error.HTTPError as exc:
        last = f'HTTP {exc.code}: {exc.read().decode(errors="replace")[:500]}'
    except Exception as exc:
        last = f'{type(exc).__name__}: {exc}'
    time.sleep(delay)
print('down:', last)
sys.exit(1)
