# Keiko ESP32-S3 hydrophone node.
#
# The ESP32-S3 has no Linux side: the MCU streams sample blocks over USB and *this Mac* plays the role the
# UNO Q's Linux side plays in firmware/unoq -- python/main.py turns the blocks into the KEIK UDP stream
# the pipeline reads. Optional: stream over Wi-Fi straight from the board, no laptop (see README).
#
# On this Mac
#   make core        one-time: install arduino-cli + the esp32:esp32 core (~600 MB)
#   make check       compile the sketch (no board needed)          make check-wifi   same, with the Wi-Fi sender compiled in
#   make flash       compile + flash over USB (PORT=/dev/cu.usbmodem*; auto-detected when there is one Espressif device)
#   make monitor     raw serial console (ctrl-] to leave) -- the block stream is binary, use `make start` instead
#   make venv        one-time: .venv with numpy + pyserial for the host side
#   make test        offline test of the Python side with synthetic blocks
#   make start       read blocks from the board over USB, print the health line, forward UDP to the pipeline
#   make listen      receive the UDP stream here (checks what the pipeline would see)
#   make record      record DURATION=30 seconds from the hydrophone into recordings/<utc>.wav
#   make start UDP_HOST=<ip>   forward to a pipeline on another machine instead of 127.0.0.1
#
# Settings (UDP destination, node id, serial port) live in python/keiko.env; real environment variables override it.

PORT     ?=
UDP_HOST ?=
DURATION ?= 30
FQBN_OPTS ?=
PYTHON   ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
ESP32_URL := https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
# esptool cannot flash through a hub-less "UART" port and a "USB" port at once; pick the native USB one by default
PORT_GUESS = $(firstword $(wildcard /dev/cu.usbmodem*) $(wildcard /dev/cu.usbserial*) $(wildcard /dev/cu.SLAB_USBtoUART))
SERIAL    = $(if $(PORT),$(PORT),$(PORT_GUESS))
ENV       = $(if $(UDP_HOST),KEIKO_UDP_HOST=$(UDP_HOST)) $(if $(PORT),KEIKO_SERIAL_PORT=$(PORT))

.PHONY: core check check-wifi flash monitor venv test start listen record port-check

# ---- toolchain -------------------------------------------------------------
core:
	@command -v arduino-cli >/dev/null || brew install arduino-cli
	arduino-cli core update-index --additional-urls $(ESP32_URL)
	arduino-cli core install esp32:esp32 --additional-urls $(ESP32_URL)

# Arduino's bundled ctags is x86-only; on Apple Silicon without Rosetta point it at Homebrew's universal-ctags
# (brew install universal-ctags). The .ino is a stub so ctags has nothing to get wrong.
CTAGS_DIR := $(shell command -v ctags >/dev/null && dirname $$(command -v ctags))
CTAGS_OPT  = $(if $(CTAGS_DIR),--build-property "tools.ctags.path=$(CTAGS_DIR)")
check:
	arduino-cli compile --profile default $(CTAGS_OPT) sketch

# Compile the Wi-Fi variant even without a wifi_config.h of your own (uses the example; restores whatever was there).
check-wifi:
	@test -e sketch/wifi_config.h && cp sketch/wifi_config.h /tmp/keiko-wifi_config.h.bak || true
	cp sketch/wifi_config.h.example sketch/wifi_config.h
	arduino-cli compile --profile default $(CTAGS_OPT) sketch; rc=$$?; \
	  if test -e /tmp/keiko-wifi_config.h.bak; then mv /tmp/keiko-wifi_config.h.bak sketch/wifi_config.h; else rm -f sketch/wifi_config.h; fi; exit $$rc

port-check:
	@test -n "$(SERIAL)" || { echo "no ESP32-S3 on USB (nothing at /dev/cu.usbmodem*). Plug the port labelled USB into this Mac, or pass PORT=/dev/cu.xxx"; exit 1; }

flash: port-check
	arduino-cli compile --profile default $(CTAGS_OPT) --upload --port $(SERIAL) sketch

monitor: port-check
	arduino-cli monitor --port $(SERIAL) --config baudrate=921600

# ---- host side -------------------------------------------------------------
venv:
	python3 -m venv .venv && .venv/bin/pip install -q -r python/requirements.txt

test:
	$(PYTHON) python/test_node.py

start: port-check
	$(ENV) $(PYTHON) python/main.py --port $(SERIAL)

listen:
	$(PYTHON) python/udp_listen.py

# Record DURATION seconds straight from the board into recordings/<utc>.wav (DC removed, 16-bit mono).
# Reads the serial stream itself, so stop `make start` first -- only one process can hold the port.
record: port-check
	@mkdir -p recordings
	$(ENV) $(PYTHON) python/main.py --port $(SERIAL) --seconds $(DURATION) --wav recordings/$$(date -u +%Y%m%dT%H%M%SZ).wav
	@ls -la recordings | tail -1
