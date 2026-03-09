# x-forge

`x-forge` is a Rust crate that automates deterministic native builds, packaging, signing, and publishing so a single GitHub release can serve every language consumer. Build targets, channels, and components come from `rust-toolchain.toml`, while `xforge.yaml` only configures `precompiled_binaries`.

## Documentation

- `docs/overview.md` — full guide covering the release loop, CLI surface area, workspace layout, adapters, and schemas.
- `docs/configuring-targets.md` — schema-driven reference for declaring build targets and adapter settings.
- `docs/release.md` — release checklist, signing notes, and automation snippets.

## Next steps

Start with `docs/overview.md` before running the CLI or inspecting adapters so you know how the workspace pieces fit together.

## Quick start

Initialize a project with defaults before building or bundling:

```bash
xforge init --manifest-dir .
```

Validate setup without writing files:

```bash
xforge init --manifest-dir . --check
```

- Rust crates: writes `rust-toolchain.toml`, `.cargo/config.toml`, and Android linker helper scripts under `scripts/`.
- Dart plugin directories (`pubspec.yaml` present): writes `xforge.yaml` with a `precompiled_binaries` template.

## Building and publishing

1. **Initialize your project** (`xforge init`) to scaffold config and linker helpers.
2. **Build for each target** using `xforge build --target <triple>` or `cargo build --target <triple>`. Libraries land under `target/<triple>/<profile>/`.
3. **Bundle artifacts** with `xforge bundle` to create archives and manifest in your dist folder.
4. **Publish** to a GitHub release with `xforge publish`, which signs and uploads everything.

For Android builds, init creates `.cargo/config.toml` linker mappings that auto-detect your NDK. Set `XFORGE_ANDROID_API` (default `23`) to override the Clang API level.

### Library requirements

XForge bundles shared objects (`.so`, `.dylib`, `.dll`) for adapters to use. Your crate must produce a shared library:

- **Linux/Android, macOS/iOS, Windows**: configure `[lib] crate-type = ["cdylib"]` in `Cargo.toml`.
  
  