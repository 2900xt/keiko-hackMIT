# Keiko UNO Q hydrophone node.
#
# On this Mac
#   make core        one-time: install arduino-cli + the arduino:zephyr core (~1 GB)
#   make check       compile the sketch locally (type check; the MCU itself is always flashed from the board's Linux side)
#   make venv        one-time: .venv with numpy + msgpack for `make test`
#   make test        offline test of the Python side with synthetic blocks
#
# On the board (default transport: USB-C + adb -- works on a fresh board, no Wi-Fi or SSH needed)
#   make start       deploy the app, compile + flash the MCU, start the Python side
#   make logs        last 30 lines of the app's output          make follow    stream it
#   make stop        stop the app                               make shell     shell on the board
#   make ip          board hostname + IP                        make listen    receive the UDP stream here (see below)
#   make record      record DURATION=30 seconds from the hydrophone into recordings/<utc>.wav on this Mac (no restart)
#
# Over Wi-Fi instead: `make enable-ssh` once over USB, then add `VIA=ssh BOARD=<ip or name.local>` to any target.
#
# App settings (UDP destination etc.) live in python/keiko.env, not app.yaml -- App Lab's manifest has no env section.
# To receive the stream on this Mac: put this Mac's IP in KEIKO_UDP_HOST there, `make start`, then `make listen`.

APP_NAME ?= keiko-unoq
APP_DIR  ?= /home/arduino/ArduinoApps/$(APP_NAME)
VIA      ?= adb
BOARD    ?= uno-q.local
# (SSH_USER, not USER: the shell already exports USER as your Mac login, and ?= would keep it)
SSH_USER ?= arduino
STAGE    ?= /tmp/$(APP_NAME)
PORT     ?= 5005
DURATION ?= 30
FQBN     := arduino:zephyr:unoq
PYTHON   ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
# adb: Homebrew's android-platform-tools if present, else the copy the arduino:zephyr core installs
ADB      ?= $(firstword $(shell command -v adb 2>/dev/null) $(wildcard $(HOME)/Library/Arduino15/packages/arduino/tools/adb/*/adb))
EXCLUDES := --exclude .venv --exclude __pycache__ --exclude '*.wav' --exclude .cache --exclude Makefile --exclude .DS_Store --exclude recordings

ifeq ($(VIA),ssh)
  RUN    = ssh $(SSH_USER)@$(BOARD)
  DEPLOY = rsync -a --delete $(EXCLUDES) ./ $(SSH_USER)@$(BOARD):$(APP_DIR)/
  PULL   = scp $(SSH_USER)@$(BOARD):
else
  RUN    = $(ADB) shell
  DEPLOY = rsync -a --delete $(EXCLUDES) ./ $(STAGE)/ && $(ADB) push $(STAGE) $(dir $(APP_DIR))
  PULL   = $(ADB) pull 
endif

.PHONY: core check venv test deploy start restart stop logs follow shell ip enable-ssh listen record adb-check

# ---- Mac-side --------------------------------------------------------------
core:
	@command -v arduino-cli >/dev/null || brew install arduino-cli
	arduino-cli core update-index
	arduino-cli core install arduino:zephyr

# Arduino's bundled ctags is x86-only; on Apple Silicon without Rosetta point it at Homebrew's universal-ctags
# (brew install universal-ctags). The .ino is a stub so ctags has nothing to get wrong.
CTAGS_DIR := $(shell command -v ctags >/dev/null && dirname $$(command -v ctags))
check:
	arduino-cli compile --profile default $(if $(CTAGS_DIR),--build-property "tools.ctags.path=$(CTAGS_DIR)") sketch

venv:
	python3 -m venv .venv && .venv/bin/pip install -q -r python/requirements.txt

test:
	$(PYTHON) python/test_node.py

listen:
	$(PYTHON) python/udp_listen.py $(PORT)

# ---- board-side ------------------------------------------------------------
adb-check:
ifneq ($(VIA),ssh)
	@test -n "$(ADB)" || { echo "adb not found: brew install android-platform-tools (or make core)"; exit 1; }
	@$(ADB) get-state >/dev/null 2>&1 || { echo "no UNO Q on USB (adb sees no device). Plug it in directly, wait ~1 min, retry."; exit 1; }
endif

deploy: adb-check
	$(RUN) "mkdir -p $(APP_DIR)"
	$(DEPLOY)

start: deploy
	$(RUN) "arduino-app-cli app restart $(APP_DIR)"

restart: start

stop: adb-check
	$(RUN) "arduino-app-cli app stop $(APP_DIR)"

logs: adb-check
	$(RUN) "arduino-app-cli app logs --tail 30 $(APP_DIR)"

follow: adb-check
	$(RUN) "arduino-app-cli app logs --follow $(APP_DIR)"

shell: adb-check
	$(RUN)

ip: adb-check
	$(RUN) "hostname; hostname -I"

# Record DURATION seconds from the hydrophone into recordings/<utc>.wav on this Mac. Captures the UDP stream on the
# board's Linux side with python/udp_listen.py, so the app keeps running (no restart, no re-flash). Needs
# KEIKO_UDP_HOST=auto (the default) so the stream reaches the board host.
record: deploy
	$(RUN) "python3 $(APP_DIR)/python/udp_listen.py --wav /tmp/keiko-rec.wav --seconds $(DURATION)"
	@mkdir -p recordings
	$(PULL)/tmp/keiko-rec.wav recordings/$$(date -u +%Y%m%dT%H%M%SZ).wav
	@ls -la recordings | tail -1

# Turns on SSH (App Lab's "network mode"). Needed once before VIA=ssh; the board must already be on Wi-Fi.
enable-ssh:
	$(ADB) shell "arduino-app-cli system network-mode enable"
