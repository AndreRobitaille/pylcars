#!/bin/bash
# Install display files only. This never flashes the ESP32.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 - "$project_dir" "${1:-}" <<'PY'
from pathlib import Path
import datetime, hashlib, os, shutil, sys
project = Path(sys.argv[1])
source = project / 'CIRCUITPY'
relative = [
    'lcars/main.bmp', 'lcars/setup.bmp',
    'lcars/antonio12.bin', 'lcars/antonio16.bin', 'lcars/antonio24.bin',
    'lib/adafruit_touchscreen.py', 'lib/pyportal_wire.py',
    'lib/pyportal_touch.py', 'lib/lcars_ui.py', 'code.py',
]
for name in relative:
    if not (source / name).is_file():
        raise SystemExit('Missing source file: ' + name)
if sys.argv[2] == '--check':
    print('All 10 LCARS installation files are present. Nothing was copied.')
    raise SystemExit(0)
if sys.argv[2]:
    raise SystemExit('Usage: bash Install_LCARS.command [--check]')
target = Path('/Volumes/CIRCUITPY')
if not target.is_dir():
    raise SystemExit('CIRCUITPY is not mounted. Restore CircuitPython first, then run this again.')
needed = sum((source / name).stat().st_size for name in relative)
if shutil.disk_usage(target).free < needed + 65536:
    raise SystemExit('CIRCUITPY needs at least %d bytes free for this installation.' % (needed + 65536))
backup = project / 'backups' / ('display-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
backup.mkdir(parents=True, mode=0o700)
for name in relative:
    old = target / name
    if old.is_file():
        saved = backup / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(old, saved)
# Assets and modules first. Replacing code.py last starts the new interface.
for name in relative:
    dest = target / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = (source / name).read_bytes()
    with dest.open('wb') as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    if hashlib.sha256(dest.read_bytes()).digest() != hashlib.sha256(payload).digest():
        raise SystemExit('Copy verification failed: ' + name)
print('SUCCESS: LCARS display files installed and verified.')
print('Previous display files saved in:', backup)
print('The PyPortal should reload. Tap still works with firmware 0.2.')
print('Long presses need the ESP32 0.3 update and a Long Press action in Apple Home.')
PY
