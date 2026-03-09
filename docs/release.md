# Precompiled Binaries (XForge)

XForge produces signed manifests, deterministic build hashes, and platform artifacts so consumer adapters can download verified binaries instead of compiling the Rust crate locally. The adapter flow mirrors the CLI publish step, which keeps `xforge-manifest.json`, signatures, and archives in sync with the GitHub release identified by `build_id`.

## How adapters resolve a binary

1. **Read `xforge.yaml`.** The adapter expects a `precompiled_binaries` block (see below). Missing this block means the adapter skips the precompiled route.
2. **Compute the `build_id`.** Every adapter uses the same hash as the CLI (Cargo.toml, Cargo.lock, rust-toolchain.toml, xforge.yaml, `.udl` inputs). The Dart adapter ships with `crate_hash.dart` to replicate the CLI hashing logic.
3. **Download the manifest.** Adapters fetch `xforge-manifest.json` and its `.sig` from the configured release URL and verify the signature using the `public_key` from `xforge.yaml`.
4. **Match the platform.** The manifest lists `platforms.targets` entries; adapters match their host triple (e.g., `aarch64-apple-darwin`) to a platform with artifacts.
5. **Download the artifact.** The first artifact listed for the matched platform is downloaded along with its `.sig` and verified with the same `public_key`.
6. **Fallback.** Unless `precompiled_binaries.mode=always`, adapters fall back to building with Cargo when download/verification fails. Some consumer builders (like `xforge_dart`'s `PrecompiledBuilder`) detect whether Rust is available and only fall back when a toolchain exists.

## Manifest and artifact requirements

- `xforge-manifest.json` and `xforge-manifest.json.sig` must be part of the release.
- Every platform archive produced by `xforge bundle` must be uploaded with a matching `.sig` file.
- The release tag must equal the manifest `build.id` so adapters can derive URLs (`<url_prefix><build_id>/<file>`).
- The manifest schema is `schemas/manifest.schema.json` and enforces entries such as `build.id`, `platforms.targets[*].artifacts`, and the optional `signing` block that `xforge publish` populates.
- `xforge publish` refuses to upload assets whose names already exist in the release; it prints `uploaded`/`skipped` lines so you can verify what changed.

## Release checklist

### 0. Initialize project config

Run `xforge init` to scaffold `rust-toolchain.toml`, `.cargo/config.toml` with Android linker mappings, and helper scripts. Validate with `--check` before proceeding.

```bash
xforge init --manifest-dir .
xforge init --manifest-dir . --check
```

Ensure your crate produces shared libraries by adding to `Cargo.toml`:

```toml
[lib]
crate-type = ["cdylib"]
```

### 1. Configure `xforge.yaml` and `rust-toolchain.toml`

Add a `precompiled_binaries` block next to `Cargo.toml` and ensure `rust-toolchain.toml` declares the targets/components.

```yaml
precompiled_binaries:
  repository: owner/repo
  public_key: "<public_key_hex>"
  url_prefix: "https://github.com/owner/repo/releases/download/"
  mode: auto
```

```toml
[toolchain]
channel = "stable"
targets = ["x86_64-unknown-linux-gnu", "aarch64-apple-darwin"]
components = ["rustfmt", "clippy"]
```

- `repository` is required and normalized to `owner/repo` (GitHub/GitHub-compatible hosts).
- `public_key` is the 32-byte hex string produced by `xforge keygen`.
- `url_prefix` overrides the GitHub download path when you host artifacts elsewhere.
- `mode` controls adapter fallbacks (`auto`, `always`/`download`, `never`/`build`/`off`).
- `toolchain.targets` tells the CLI which Rust triples to build. See `docs/configuring-targets.md` for the full schema and valid triples.
- `[lib] crate-type = ["cdylib"]` ensures shared libraries are built for bundling.

### 2. Build each target

Run `xforge build --target <triple>` (or `cargo build --target`, `cross build`, etc.) for each platform listed in `toolchain.targets`. `xforge build` prints `build_id` and the shared-library path for the target it just built. The next step assumes the artifacts exist under `target/<triple>/<profile>`.

### 3. Bundle artifacts and manifest

```bash
xforge bundle --output-dir dist --profile release
```

or, while the CLI is still under active development:

```bash
cargo run -p xforge-cli -- bundle --manifest-dir . --output-dir dist --profile release
```

This command writes `dist/xforge-manifest.json`, `dist/build_id.txt`, and one archive per target (tar.gz/zip depending on the platform). Inspect the manifest; it includes the `build.id`, `platforms.targets`, and empty binding list that shared adapters expect.

### 4. Publish and sign

1. Generate keys:

   ```bash
   cargo run -p xforge-cli -- keygen
   ```

   Copy the `public_key` into `xforge.yaml` and keep `private_key` secret.
2. Set environment variables:

   ```bash
   export XFORGE_PRIVATE_KEY="<private_key_hex>"
   export GITHUB_TOKEN="<token with repo scope>"
   ```
3. Run publish:

   ```bash
   cargo run -p xforge-cli -- publish --manifest dist/xforge-manifest.json --assets-dir dist --out-dir dist
   ```

`xforge publish` signs the manifest and every asset (creating `.sig` files), verifies the manifest signature, and uploads everything to a release tagged `build_id`. It reads `precompiled_binaries.repository` when `--repository` is omitted, so keep that block consistent with your GitHub repo. The CLI reuses existing releases and skips uploading assets that already exist.

`xforge sign`/`verify` are also available for non-manifest files when you need to manage signatures manually.

### Optional: validate the release locally

The Dart adapter ships with a validation CLI: `dart run xforge_dart validate-precompiled [--crate-dir] [--build-id] [--target]`. Running it from your workspace ensures the manifest and a platform artifact can be downloaded and verified with the public key before relying on the release in production.

## Sample GitHub Actions snippet

```yaml
on:
  push:
    branches: [ main ]
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          path: crate
      - uses: actions/checkout@v4
        with:
          repository: nuCode-Tech/x-forge
          path: x-forge
      - uses: dtolnay/rust-toolchain@stable
      - run: |
          cargo run --manifest-path ./x-forge/crates/xforge-cli/Cargo.toml -- bundle \
            --manifest-dir ./crate \
            --output-dir ./crate/dist \
            --profile release
      - name: Publish release
        env:
          XFORGE_PRIVATE_KEY: ${{ secrets.XFORGE_PRIVATE_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          cargo run --manifest-path ./x-forge/crates/xforge-cli/Cargo.toml -- publish \
            --manifest ./crate/dist/xforge-manifest.json \
            --assets-dir ./crate/dist
```

This example builds on Ubuntu and reuses the `xforge-cli` workspace binary. Adjust the matrix (`macos-latest`, `windows-latest`) and include Android targets in `rust-toolchain.toml` when you need Android archives.

## Android targets

Android targets require the NDK so `xforge bundle` can include `.so` files. On Ubuntu runners install the Android command-line tools, accept licenses, and install the NDK version you plan to ship. For example:

```bash
sudo apt-get update && sudo apt-get install -y wget unzip
wget https://dl.google.com/android/repository/commandlinetools-linux-108-9123335_latest.zip -O tools.zip
mkdir -p $HOME/android-sdk/cmdline-tools
unzip tools.zip -d $HOME/android-sdk/cmdline-tools
yes | $HOME/android-sdk/cmdline-tools/tools/bin/sdkmanager --sdk_root=$HOME/android-sdk "platform-tools" "ndk;24.0.8215888"
```

Initialize linker wrappers once:

```bash
cargo run -p xforge-cli -- init --manifest-dir .
```

This creates `.cargo/config.toml` and `scripts/xforge-android-linker.sh` wrappers that auto-detect NDK locations (`XFORGE_ANDROID_NDK`, `ANDROID_NDK_HOME`, `ANDROID_NDK_ROOT`, `ANDROID_SDK_ROOT`, `ANDROID_HOME`) and use `XFORGE_ANDROID_API` (default `23`) for Clang selection.

Then build Android targets normally (for example, `cargo build --target=aarch64-linux-android`) before running `xforge bundle`. `bundle` still reads built libraries from `target/<triple>/<profile>`.

## Troubleshooting

- **Missing `precompiled_binaries`.** Adapters fall back to local builds; add the block to `xforge.yaml` to enable downloads.
- **Manifest or artifact signature fails.** Verify that the public key in `xforge.yaml` matches the private key used by `xforge publish`. You can test locally with `xforge verify` or `dart run xforge_dart validate-precompiled`.
- **Release missing files.** Ensure `dist` (or your `--output-dir`) contains both archives and their `.sig` siblings before running `xforge publish`. Each artifact must include the `build_id` in its name so the CLI can validate it.
