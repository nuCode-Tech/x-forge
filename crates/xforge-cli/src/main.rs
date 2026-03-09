use std::path::{Path, PathBuf};

use clap::{Parser, Subcommand};

mod commands;

#[derive(Parser)]
#[command(name = "xforge", version, about = "XForge CLI")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Initialize XForge config for a Rust crate or Dart plugin.
    Init {
        /// Directory to initialize.
        #[arg(long, default_value = ".")]
        manifest_dir: PathBuf,
        /// Overwrite files if they already exist.
        #[arg(long)]
        force: bool,
        /// Validate configuration and linker setup without writing files.
        #[arg(long)]
        check: bool,
    },
    /// Build the crate for a single target.
    Build {
        /// Manifest directory containing Cargo.toml.
        #[arg(long, default_value = ".")]
        manifest_dir: PathBuf,
        /// Target triple (overrides rust-toolchain.toml).
        #[arg(long)]
        target: Option<String>,
        /// Cargo profile (default: release).
        #[arg(long, default_value = "release")]
        profile: String,
        /// Build executor (cargo | cross | zigbuild).
        #[arg(long, default_value = "cargo")]
        executor: String,
        /// Cross image to use (required for cross builds).
        #[arg(long)]
        cross_image: Option<String>,
    },
    /// Bundle built artifacts into archives + manifest.
    Bundle {
        /// Manifest directory containing Cargo.toml.
        #[arg(long, default_value = ".")]
        manifest_dir: PathBuf,
        /// Output directory for artifacts.
        #[arg(long, default_value = "dist")]
        output_dir: PathBuf,
        /// Target triple (overrides rust-toolchain.toml).
        #[arg(long)]
        target: Option<String>,
        /// Cargo profile (default: release).
        #[arg(long, default_value = "release")]
        profile: String,
    },
    /// Generate an Ed25519 keypair (public + private hex).
    Keygen,
    /// Sign a file with XFORGE_PRIVATE_KEY and write a .sig file.
    Sign {
        /// File to sign.
        #[arg(long)]
        file: PathBuf,
        /// Output signature path (defaults to <file>.sig).
        #[arg(long)]
        out: Option<PathBuf>,
    },
    /// Verify a file against a signature and public key.
    Verify {
        /// File to verify.
        #[arg(long)]
        file: PathBuf,
        /// Signature file.
        #[arg(long)]
        signature: PathBuf,
        /// Public key hex string.
        #[arg(long, conflicts_with = "public_key_file")]
        public_key: Option<String>,
        /// File containing public key hex string.
        #[arg(long)]
        public_key_file: Option<PathBuf>,
    },
    /// Sign manifest + assets for publishing.
    Publish {
        /// Manifest file to sign.
        #[arg(long, default_value = "xforge-manifest.json")]
        manifest: PathBuf,
        /// Repository slug (owner/repo). If omitted, read from xforge.yaml.
        #[arg(long)]
        repository: Option<String>,
        /// Directory of assets to sign (non-recursive).
        #[arg(long)]
        assets_dir: Option<PathBuf>,
        /// Individual asset files to sign.
        #[arg(long = "asset")]
        assets: Vec<PathBuf>,
        /// Output directory for signed artifacts/signatures.
        #[arg(long)]
        out_dir: Option<PathBuf>,
    },
}

fn main() {
    if let Err(message) = run_cli() {
        let _ = exit_with_error(&message);
    }
}

fn run_cli() -> Result<(), String> {
    let cli = Cli::parse();
    match cli.command {
        Command::Init {
            manifest_dir,
            force,
            check,
        } => {
            let outcome = commands::init::run(commands::init::InitArgs {
                manifest_dir,
                force,
                check,
            })?;
            println!("project_kind={}", outcome.project_kind);
            for file in outcome.created_files {
                println!("created={}", file.display());
            }
            for file in outcome.skipped_files {
                println!("skipped={}", file.display());
            }
            for line in outcome.checks {
                println!("check={}", line);
            }
            Ok(())
        }
        Command::Keygen => {
            let output = commands::keygen::run()?;
            println!("public_key={}", output.public_key_hex);
            println!("private_key={}", output.private_key_hex);
            Ok(())
        }
        Command::Build {
            manifest_dir,
            target,
            profile,
            executor,
            cross_image,
        } => {
            let executor = match executor.as_str() {
                "cargo" => commands::build::BuildExecutorKind::Cargo,
                "cross" => commands::build::BuildExecutorKind::Cross,
                "zigbuild" => commands::build::BuildExecutorKind::Zigbuild,
                other => {
                    return exit_with_error(&format!(
                        "invalid executor '{}'; expected cargo, cross, or zigbuild",
                        other
                    ));
                }
            };
            let outcome = commands::build::run(commands::build::BuildArgs {
                manifest_dir,
                target,
                profile,
                executor,
                cross_image,
            })?;
            println!("build_id={}", outcome.build_id);
            println!("library={}", outcome.library_path.display());
            Ok(())
        }
        Command::Bundle {
            manifest_dir,
            output_dir,
            target,
            profile,
        } => {
            let outcome = commands::bundle::run(commands::bundle::BundleArgs {
                manifest_dir,
                target,
                output_dir,
                profile,
            })?;
            println!("build_id={}", outcome.build_id);
            println!("manifest={}", outcome.manifest_path.display());
            for archive in outcome.archive_paths {
                println!("archive={}", archive.display());
            }
            Ok(())
        }
        Command::Sign { file, out } => {
            let private_key_hex = std::env::var("XFORGE_PRIVATE_KEY")
                .map_err(|_| "Missing XFORGE_PRIVATE_KEY environment variable".to_string())?;
            let out_path = commands::sign::run(commands::sign::SignArgs {
                file,
                out,
                private_key_hex,
            })?;
            println!("signature={}", out_path.display());
            Ok(())
        }
        Command::Verify {
            file,
            signature,
            public_key,
            public_key_file,
        } => {
            let public_key_hex = match (public_key, public_key_file) {
                (Some(hex), None) => hex,
                (None, Some(path)) => std::fs::read_to_string(&path).map_err(|err| {
                    format!("failed to read public key file '{}': {}", path.display(), err)
                })?,
                _ => {
                    return exit_with_error(
                        "Provide exactly one of --public-key or --public-key-file",
                    );
                }
            };
            let ok = commands::verify::run(commands::verify::VerifyArgs {
                file,
                signature,
                public_key_hex: public_key_hex.trim().to_string(),
            })?;
            if ok {
                println!("OK");
                Ok(())
            } else {
                exit_with_error("INVALID SIGNATURE")
            }
        }
        Command::Publish {
            manifest,
            repository,
            assets_dir,
            assets,
            out_dir,
        } => {
            let private_key_hex = std::env::var("XFORGE_PRIVATE_KEY")
                .map_err(|_| "Missing XFORGE_PRIVATE_KEY environment variable".to_string())?;
            let github_token = std::env::var("GITHUB_TOKEN")
                .map_err(|_| "Missing GITHUB_TOKEN environment variable".to_string())?;
            let repository = match repository {
                Some(value) => value,
                None => {
                    let manifest_dir = manifest
                        .parent()
                        .map(|path| path.to_path_buf())
                        .unwrap_or_else(|| PathBuf::from("."));
                    let settings = resolve_precompiled_settings(&manifest_dir)?
                        .ok_or_else(|| "missing precompiled_binaries.repository in xforge.yaml".to_string())?;
                    settings.repository
                }
            };
            let result = commands::publish::run(commands::publish::PublishArgs {
                manifest,
                assets_dir,
                asset_files: assets,
                out_dir,
                repository,
                github_token,
                private_key_hex,
            })?;
            for output in result.signed_files {
                println!("{}", output.display());
            }
            for name in result.uploaded {
                println!("uploaded: {}", name);
            }
            for name in result.skipped {
                println!("skipped: {}", name);
            }
            if let Some(url) = result.release_url {
                println!("release: {}", url);
            }
            Ok(())
        }
    }
}

fn resolve_precompiled_settings(
    manifest_dir: &Path,
) -> Result<Option<xforge_core::config::PrecompiledSettings>, String> {
    let mut current = Some(manifest_dir);
    while let Some(dir) = current {
        let settings = xforge_core::config::precompiled_settings(dir)
            .map_err(|err| err.to_string())?;
        if settings.is_some() {
            return Ok(settings);
        }
        current = dir.parent();
    }
    Ok(None)
}

fn exit_with_error(message: &str) -> Result<(), String> {
    eprintln!("{}", message);
    std::process::exit(1);
}
