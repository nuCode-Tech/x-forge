# x-forge overview

`x-forge` is a Rust workspace and CLI that automates deterministic native builds, packaging, signing, and publishing so a single GitHub release can serve every language consumer. The manifest and artifact naming are content-addressed (`build_id`) and enforced by `xforge-core`, while adapters remain thin by downloading prebuilt binaries instead of guessing ABI rules.

## Deterministic release loop

1. `xforge build` compiles a single Rust target with Cargo/Cross/Zigbuild, computes the `build_id`, and exposes where the shared library landed. Target triples (see `crates/xforge-core/src/platform/key.rs`) drive ABI identity so the same inputs always hash to the same release ID.
2. `xforge bundle` packages every configured target directory into archives, writes `xforge-manifest.json`, and records `build_id.txt`. The CLI relies on `xforge-pack` to emit tar/zip archives whose names include the `build_id` and target.
3. `xforge publish` signs the manifest and artifacts, then creates or reuses a GitHub release tagged with the `build_id`. `xforge publish` uploads each signed asset only once, so repeated runs are safe, and it automatically reads `precompiled_binaries.repository` from `xforge.yaml` when `--repository` is omitted. See `docs/release.md` for the end-to-end checklist.

## CLI reference

- `xforge keygen` — produce a new Ed25519 pair (`public_key` for manifests, `private_key` for publishing).
- `xforge build [--target <triple>] [--profile <name>] [--executor cargo|cross|zigbuild] [--cross-image <image>]` — compile a single target; defaults to the first entry in `rust-toolchain.toml`. Prints `build_id` and the built library path.
- `xforge bundle [--target <triple>] [--profile release] [--output-dir dist]` — package the existing build output for every configured target, write `xforge-manifest.json`, and emit `build_id.txt`. It assumes the appropriate libraries already exist under `target/<triple>/<profile>`. The manifest and archives live in `--output-dir` (defaults to `dist`).
- `xforge sign --file <path> [--out <path>]` — sign any file with `XFORGE_PRIVATE_KEY` and save a `.sig` sibling.
- `xforge verify --file <path> --signature <path> --public-key <hex>` — verify a signature against a public key; use `--public-key-file` to read the key from disk.
- `xforge publish --manifest dist/xforge-manifest.json [--assets-dir dist] [--asset PATH]* [--out-dir dist] [--repository owner/repo]` — sign the manifest+assets, upload them to a GitHub release named after the `build_id`, and print which files were uploaded/skipped along with the release URL. Requires `XFORGE_PRIVATE_KEY` and `GITHUB_TOKEN` in the environment. When `--repository` is omitted the CLI infers the owner/repo from `xforge.yaml`'s `precompiled_binaries.repository`.

When the CLI is not installed, run it via `cargo run -p xforge-cli -- <command>` or install it from the workspace (`cargo install --path crates/xforge-cli`).

## Workspace layout

```
x-forge/
├── crates/          # rust workspace modules (core, build, pack, publish, cli)
├── adapters/        # language consumers (Dart adapter shipped, others placeholders)
├── schemas/         # public JSON schemas for config and manifest
├── docs/            # guidance on target config and release flow
```

## Configuration & schemas

`rust-toolchain.toml` declares the Rust channel, targets, and components that XForge uses when building. `xforge.yaml` sits beside `Cargo.toml` and only declares the `precompiled_binaries` block that adapters consume. See `docs/configuring-targets.md` for the schema-driven guidance and `schemas/config.schema.json` for the authoritative JSON schema. The manifest emitted by `xforge bundle` conforms to `schemas/manifest.schema.json`, so adapters can download artifacts with confidence.

## Language adapters

- `adapters/dart` (`xforge_dart`) — runtime builder + CLI for Flutter/Dart consumers. It exposes `PrecompiledBuilder` for `code_assets`, downloads signed artifacts by reading `xforge.yaml`, computes the same `build_id` as the CLI (including `rust-toolchain.toml`), verifies every manifest/artifact signature, and falls back to a local build depending on `precompiled_binaries.mode`. The companion CLI (`dart run xforge_dart validate-precompiled [--crate-dir …] [--build-id …] [--target …]`) confirms a release can be downloaded and verified.
- `adapters/python` (`xforge-python`) — Python adapter that mirrors the Dart flow: reads `xforge.yaml`, computes `build_id` (same algorithm as the CLI), downloads and verifies signed manifest/artifacts, and exposes `get_library_path` / `load_native_library` for generated bindings. CLI: `xforge keygen`, `xforge validate-precompiled`. See `adapters/python/README.md` for integration.
- `adapters/gradle`, `adapters/swift` — reserved for future Kotlin/Gradle and Swift (SPM/CocoaPods) adapters; currently README-only stubs.

## Additional docs

- `docs/configuring-targets.md` — how `rust-toolchain.toml` expresses targets, toolchain choices, and the `precompiled_binaries` settings adapters rely on.
- `docs/release.md` — step-by-step release flow (build, bundle, publish, sign) plus publishing quirks and sample automation snippets.

## Schemas

- `schemas/config.schema.json` — validates `xforge.yaml` (precompiled repository/public_key).
- `schemas/manifest.schema.json` — validates the manifest published with each release (package info, build identity, artifacts, platforms, signing block).
