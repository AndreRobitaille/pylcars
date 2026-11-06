#!/bin/bash
# Build only. This script never opens a serial port or writes to the PyPortal.
set -euo pipefail
umask 077
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
toolchain_dir="$project_dir/.toolchain"
mkdir -p "$toolchain_dir/bin" "$toolchain_dir/data" "$toolchain_dir/downloads" \
  "$toolchain_dir/user" "$toolchain_dir/cache" "$project_dir/logs"
build_log="$project_dir/logs/build.log"
if [[ "${PYP_LOG_ACTIVE:-}" != 1 ]]; then
  PYP_LOG_ACTIVE=1 /bin/bash "${BASH_SOURCE[0]}" "$@" 2>&1 | tee "$build_log"
  exit "${PIPESTATUS[0]}"
fi

failed() {
  local code=$?
  printf '\nBuild stopped. Nothing was flashed. Details are in:\n%s\n' "$build_log"
  exit "$code"
}
trap failed ERR

if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  printf 'This build package targets the Apple Silicon Mac used for this project.\n'
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3 is required. No installation was attempted.\n'
  exit 1
fi

cli_archive="$toolchain_dir/downloads/arduino-cli_1.5.1_macOS_ARM64.tar.gz"
cli_url='https://github.com/arduino/arduino-cli/releases/download/v1.5.1/arduino-cli_1.5.1_macOS_ARM64.tar.gz'
cli_sha='cb952e8c1621c95ef5f1d17831c945e3d0ec5973f89c557a7ec8feb9c4f7d4c9'
if [[ ! -f "$cli_archive" ]]; then
  printf 'Downloading Arduino CLI 1.5.1 from Arduino...\n'
  curl --fail --location --retry 3 --proto '=https' --tlsv1.2 \
    --output "$cli_archive.part" "$cli_url"
  mv "$cli_archive.part" "$cli_archive"
fi
printf '%s  %s\n' "$cli_sha" "$cli_archive" | shasum -a 256 -c -
tar -xzf "$cli_archive" -C "$toolchain_dir/bin" arduino-cli
cli="$toolchain_dir/bin/arduino-cli"
config="$toolchain_dir/arduino-cli.yaml"

# JSON is valid YAML and keeps paths containing spaces properly quoted.
python3 - "$toolchain_dir" "$config" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
data = {
    'board_manager': {'additional_urls': [
        'https://espressif.github.io/arduino-esp32/package_esp32_index.json']},
    'directories': {
        'data': str(root / 'data'),
        'downloads': str(root / 'downloads'),
        'user': str(root / 'user'),
    },
    'build_cache': {'path': str(root / 'cache')},
    'network': {'connection_timeout': '300s'},
}
pathlib.Path(sys.argv[2]).write_text(json.dumps(data, indent=2) + '\n')
PY

if [[ "${1:-}" != '--offline' ]]; then
  printf '\nInstalling the pinned ESP32 tools and HomeSpan library.\n'
  printf 'First-time downloads can take several minutes. All tools stay in this project.\n'
  "$cli" --config-file "$config" core update-index
  "$cli" --config-file "$config" core install esp32:esp32@3.3.8
  "$cli" --config-file "$config" lib install HomeSpan@2.1.8
fi

# Our application is standard C++, with explicit declarations. The mandatory
# Arduino .ino is empty, so its automatic prototype generator has no work.
# Arduino still tries to launch an Intel-only ctags on Apple Silicon; skip
# that unused step only after verifying the .ino has no executable content.
python3 - "$project_dir" <<'PY'
from pathlib import Path
import sys
project = Path(sys.argv[1])
sketch = project / 'esp32' / 'PyPortalHomeKit'
expected = '// Empty Arduino entry file. Implementation is in app.cpp.'
ino = sketch / 'PyPortalHomeKit.ino'
if ino.read_text().strip() != expected:
    raise SystemExit('The .ino changed; restore it before bypassing prototype generation.')
if not (project / '.toolchain/data/packages/esp32/hardware/esp32/3.3.8/platform.txt').is_file():
    raise SystemExit('ESP32 core 3.3.8 is not installed. Run without --offline.')
properties = project / '.toolchain/user/libraries/HomeSpan/library.properties'
if not properties.is_file() or 'version=2.1.8' not in properties.read_text().splitlines():
    raise SystemExit('HomeSpan 2.1.8 is not installed. Run without --offline.')
PY

printf '\nBuilding the PyPortal HomeKit firmware...\n'
run_stamp="$(date +%Y%m%d-%H%M%S)"
build_dir="$project_dir/builds/$run_stamp"
output_dir="$build_dir/firmware"
mkdir -p "$output_dir"
# Compile only the reviewed sources. Finder may leave older " 2" copies beside
# them; keep those files untouched and exclude them from the staged sketch.
staged_sketch="$build_dir/sketch/PyPortalHomeKit"
mkdir -p "$staged_sketch"
cp "$project_dir/esp32/PyPortalHomeKit/PyPortalHomeKit.ino" \
   "$project_dir/esp32/PyPortalHomeKit/app.cpp" \
   "$project_dir/esp32/PyPortalHomeKit/Protocol.h" "$staged_sketch/"
"$cli" --config-file "$config" compile \
  --fqbn 'esp32:esp32:esp32:FlashMode=dio,FlashFreq=40,FlashSize=4M,PartitionScheme=min_spiffs,PSRAM=disabled' \
  --build-property 'tools.ctags.cmd.path=/usr/bin/true' \
  --warnings all --jobs 4 \
  --build-path "$build_dir/compile" --output-dir "$output_dir" \
  "$staged_sketch"

python3 - "$project_dir" "$output_dir" <<'PY'
import hashlib, json, pathlib, sys
project = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
names = ('PyPortalHomeKit.ino.bin', 'PyPortalHomeKit.ino.bootloader.bin',
         'PyPortalHomeKit.ino.partitions.bin')
for name in names:
    path = out / name
    if not path.is_file() or not path.stat().st_size:
        raise SystemExit('Missing build output: ' + name)
if (out / names[0]).stat().st_size > 0x1E0000:
    raise SystemExit('Firmware does not fit the selected app partition.')
records = []
for path in sorted(out.glob('*.bin')):
    records.append({'name': path.name, 'bytes': path.stat().st_size,
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
manifest = {'prototype': '0.3.0', 'arduino_cli': '1.5.1',
            'esp32_core': '3.3.8', 'homespan': '2.1.8', 'files': records}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(project / 'latest-build.txt').write_text(str(out) + '\n')
print('Build artifacts verified:', out)
PY
"$cli" --config-file "$config" version
"$cli" --config-file "$config" core list
"$cli" --config-file "$config" lib list
printf '\nBUILD COMPLETE. Nothing was flashed.\n'
printf 'Build finished; review the firmware before flashing.\n'
