# Keiko UNO Q hydrophone node.
#
#   make core      one-time: install arduino-cli + the arduino:zephyr core on this Mac
#   make check     compile the sketch locally (syntax/type check only — the MCU can only be flashed from the board)
#   make deploy    copy this app to the board
#   make start     compile + flash the sketch and start the Python side, on the board
#   make logs      tail the app's output
#   make stop
#
# BOARD is the UNO Q's hostname or IP (ssh user is `arduino`).

BOARD    ?= arduino-uno-q.local
USER     ?= arduino
APP_DIR  ?= ArduinoApps/keiko-unoq
FQBN     := arduino:zephyr:unoq
SSH      := ssh $(USER)@$(BOARD)
PYTHON   ?= python3   # needs numpy (pip install -r python/requirements.txt)

.PHONY: core check deploy start stop logs test

core:
	@command -v arduino-cli >/dev/null || brew install arduino-cli
	arduino-cli core update-index
	arduino-cli core install arduino:zephyr

# Arduino's bundled ctags is x86-only; on Apple Silicon without Rosetta point it at Homebrew's universal-ctags
# (brew install universal-ctags). The .ino is a stub so ctags has nothing to get wrong.
CTAGS_DIR := $(shell command -v ctags >/dev/null && dirname $$(command -v ctags))
check:
	arduino-cli compile --profile default $(if $(CTAGS_DIR),--build-property "tools.ctags.path=$(CTAGS_DIR)") sketch

deploy:
	$(SSH) "mkdir -p $(APP_DIR)"
	rsync -av --delete --exclude '*.wav' --exclude '__pycache__' ./ $(USER)@$(BOARD):$(APP_DIR)/

start: deploy
	$(SSH) "arduino-app-cli app start ~/$(APP_DIR)"

stop:
	$(SSH) "arduino-app-cli app stop ~/$(APP_DIR)"

logs:
	$(SSH) "arduino-app-cli app logs ~/$(APP_DIR)"

test:
	$(PYTHON) python/test_node.py
