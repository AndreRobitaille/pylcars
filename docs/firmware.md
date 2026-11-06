# ESP32 firmware

The PyPortal has separate SAMD51 and ESP32 processors. CircuitPython runs the
screen on the SAMD51. HomeSpan firmware runs on the ESP32. An ESP32 `.bin` file
is flashed through a temporary USB passthrough program, not copied to PORTALBOOT.

## Build

On an Apple Silicon Mac with Python 3, run from the repository directory:

```bash
bash Build_Controller.command
```

This downloads pinned Arduino tools into `.toolchain/`, verifies the CLI archive,
and builds the application. It never accesses the board or flashes firmware.
The output directory is recorded in `latest-build.txt`. Each build includes a
SHA-256 manifest and separate application, bootloader, partition, and merged images.

The Arduino board profile is:

```text
esp32:esp32:esp32:FlashMode=dio,FlashFreq=40,FlashSize=4M,PartitionScheme=min_spiffs,PSRAM=disabled
```

## First installation

This replaces the ESP32's existing firmware and saved configuration.

1. Double-press the PyPortal's Reset button to mount **PORTALBOOT**.
2. Copy the official [PyPortal ESP32 passthrough UF2](https://cdn-learn.adafruit.com/assets/assets/000/123/157/original/PyPortal_M4_ESP_32_Passthrough_TinyUSB_2023_07_30.uf2) onto it.
3. The drive disappears and a USB serial port appears. Run:

   ```bash
   bash Inspect_ESP32.command
   ```

4. Confirm the detected device is the original ESP32 with **4 MB flash**. Set
   the port below to the actual port reported by that inspection:

   ```bash
   pylcars_port=/dev/cu.usbmodemYOUR_PORT
   pylcars_esptool="$PWD/.toolchain/data/packages/esp32/tools/esptool_py/5.2.0/esptool"
   pylcars_firmware="$(cat latest-build.txt)"
   "$pylcars_esptool" --chip esp32 --port "$pylcars_port" \
     --before no-reset --after no-reset --baud 115200 \
     write-flash --compress 0x0 "$pylcars_firmware/PyPortalHomeKit.ino.merged.bin"
   ```

5. Keep USB connected until writing and hash verification finish.
6. Double-press Reset, then copy [CircuitPython 10.3.1](https://downloads.circuitpython.org/bin/pyportal/en_US/adafruit-circuitpython-pyportal-en_US-10.3.1.uf2) onto **PORTALBOOT**.
7. When **CIRCUITPY** returns, install the display files and pair through Apple Home.

The passthrough uses 115200 baud. A transfer can take about five minutes.
Adafruit documents the underlying process in its [AirLift firmware guide](https://learn.adafruit.com/upgrading-esp32-firmware/upgrade-all-in-one-esp32-airlift-firmware).

## Updating an existing installation

An application-only update can preserve Wi-Fi and HomeKit pairing data. For
the profile above, NVS occupies `0x9000` through `0xdfff`, OTA selection occupies
`0xe000` through `0xffff`, and the first application starts at `0x10000`.

Before an application-only update, verify the connected device, compare the
partition table, and confirm which application slot the bootloader will use.
Back up NVS privately and verify the backup before writing, then verify NVS
again after the application update. Do not use a merged image to preserve settings.

On this PyPortal USB passthrough, esptool's stub bulk read failed with an
`Invalid SLIP escape` error. The ESP32 ROM read worked using:

```bash
"$pylcars_esptool" --chip esp32 --port "$pylcars_port" \
  --before no-reset --after no-reset --baud 115200 --no-stub \
  read-flash --flash-size 4MB 0x9000 0x5000 /private/local/path/nvs.bin
```

That ROM path returns data in acknowledged 64-byte blocks. After a serial
failure, unplug and reconnect the board while the passthrough is installed.
Never commit the resulting backup. The board-specific updater from development
is omitted because its device identity and firmware checks were specific to
that installation.
