# Configuring Target Platforms

XForge reads `rust-toolchain.toml` to decide which targets to build, which channel to use, and which components to install. The canonical registry of supported triples lives inside `crates/xforge-core/src/platform/key.rs`; every triple you list must match one of the `PlatformKey::as_str()` values defined there.

## Declare defaults in `rust-toolchain.toml`

You can scaffold defaults with:

```bash
xforge init --manifest-dir .
```

That command writes `rust-toolchain.toml` for Rust crates and skips existing files unless `--force` is set. Validate the setup with `--check` to verify config and linker scripts are present.

Create a `rust-toolchain.toml` with a `[toolchain]` section so `xforge build` and `xforge bundle` know what to build/package. The CLI will iterate through this list, hash each target's inputs, and include the triples in the manifest.

```toml
[toolchain]
channel = "stable"
targets = [
  "x86_64-unknown-linux-gnu",
  "aarch64-linux-android",
  "aarch64-apple-darwin",
  "x86_64-pc-windows-msvc",
]
components = ["rustfmt", "clippy"]
```

- `toolchain.targets` is required; the CLI rejects invalid or unsupported target triples (see `PlatformKey` for the authoritative list).
- `xforge build` picks the first entry as its default target unless you override it with `--target`, so keep the list ordered by your primary consumer.
- `xforge bundle` packages every listed target by reading the already-built libraries under `target/<triple>/<profile>`; run `xforge build` (or `cargo build`/`cross build`) for each triple before bundling.

## Toolchain settings

`toolchain.channel` and `toolchain.components` are required so the CLI can reproduce the same rustup configuration across builds. `xforge build` and `xforge bundle` always use the `toolchain.targets` list you declare.

## Precompiled binaries block

Adapters and language-specific builders read the `precompiled_binaries` block to know where to download signed artifacts and which public key should verify them.

```yaml
precompiled_binaries:
  repository: owner/repo
  public_key: "<public_key_hex>"
  url_prefix: "https://github.com/owner/repo/releases/download/"
  mode: auto
```

- `repository` is required and is normalized to `owner/repo` (GitHub or GitHub-compatible hosts).
- `public_key` must be the 32-byte hex string produced by `xforge keygen` and is used both when signing a manifest in `xforge publish` and when adapters verify it.
- `url_prefix` overrides the default GitHub download URL when you host artifacts elsewhere.
- `mode` controls what happens when precompiled binaries cannot be found: `auto` prefers downloads but falls back to building locally, `always` treats missing/invalid binaries as an error, and `never` forces a local build. Additional aliases (`download`→`always`, `build`/`off`/`disabled`→`never`) are accepted.
- The CLI also consults this block to infer the repository when you omit `--repository` from `xforge publish`.

See `docs/release.md` for the full release flow (bundle, sign, publish) that relies on this configuration.

## Missing `rust-toolchain.toml`

`xforge build` and `xforge bundle` require a `rust-toolchain.toml` in the crate directory or repo root. If the file is missing or the required fields are absent, the CLI exits with a configuration error.

## Shared library output (cdylib)

XForge bundles rely on shared objects (`.so`, `.dylib`, `.dll`). Ensure your Rust crate is configured to produce them:

```toml
[lib]
crate-type = ["cdylib"]
```

Without this, `cargo build --target <triple>` will produce only `.rlib` (static) or metadata formats, which `xforge bundle` cannot package. If you want both static and dynamic libraries, use `crate-type = ["cdylib", "rlib"]`.

## Android linker helpers

When you run `xforge init` in a Rust crate, it also creates:

- `.cargo/config.toml` target linker entries for `aarch64-linux-android`, `armv7-linux-androideabi`, and `x86_64-linux-android`
- `scripts/xforge-android-linker.sh` plus per-target wrapper scripts

The linker script auto-detects the NDK from `XFORGE_ANDROID_NDK`, `ANDROID_NDK_HOME`, `ANDROID_NDK_ROOT`, or SDK install directories and uses `XFORGE_ANDROID_API` (default `23`) to select the correct Clang driver.
