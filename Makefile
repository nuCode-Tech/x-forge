PYTHON_ADAPTER := adapters/python
DART_ADAPTER   := adapters/dart

# ──────────────────────────────────────────────────────────────────────────────
# Python adapter
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: python-install
python-install:
	pip install -e "$(PYTHON_ADAPTER)[dev]"

.PHONY: python-test
python-test:
	cd $(PYTHON_ADAPTER) && python3 -m pytest tests/ -v

.PHONY: python-codegen
## Generate _xforge_loader.py for a consumer package.
## Usage: make python-codegen CRATE_DIR=path/to/crate OUT=path/to/_xforge_loader.py
python-codegen:
	python3 -m xforge.tool.cli generate-loader \
		$(if $(CRATE_DIR),--crate-dir "$(CRATE_DIR)") \
		$(if $(OUT),--out "$(OUT)")

# ──────────────────────────────────────────────────────────────────────────────
# Dart adapter
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: dart-get
dart-get:
	cd $(DART_ADAPTER) && dart pub get

.PHONY: dart-test
dart-test:
	cd $(DART_ADAPTER) && dart test

.PHONY: dart-codegen
## Generate an xforge loader for a consumer Dart package.
## Usage: make dart-codegen CRATE_DIR=path/to/crate OUT=path/to/loader.dart
dart-codegen:
	cd $(DART_ADAPTER) && dart run tool/cli.dart generate-loader \
		$(if $(CRATE_DIR),--crate-dir "$(CRATE_DIR)") \
		$(if $(OUT),--out "$(OUT)")

# ──────────────────────────────────────────────────────────────────────────────
# Rust (xforge-cli)
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: rust-test
rust-test:
	cargo test

.PHONY: rust-build
rust-build:
	cargo build --release

# ──────────────────────────────────────────────────────────────────────────────
# Aggregate
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: test
test: rust-test python-test dart-test

.PHONY: codegen
## Run codegen for all adapters (set CRATE_DIR and OUT per adapter as needed).
codegen: python-codegen dart-codegen
