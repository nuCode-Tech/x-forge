use std::fs;
use std::path::{Path, PathBuf};

pub struct InitArgs {
    pub manifest_dir: PathBuf,
    pub force: bool,
    pub check: bool,
}

pub struct InitOutcome {
    pub project_kind: String,
    pub created_files: Vec<PathBuf>,
    pub skipped_files: Vec<PathBuf>,
    pub checks: Vec<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ProjectKind {
    DartPlugin,
    Rust,
}

impl ProjectKind {
    fn as_str(self) -> &'static str {
        match self {
            ProjectKind::DartPlugin => "dart-plugin",
            ProjectKind::Rust => "rust",
        }
    }
}

pub fn run(args: InitArgs) -> Result<InitOutcome, String> {
    if !args.manifest_dir.exists() {
        return Err(format!(
            "manifest dir '{}' does not exist",
            args.manifest_dir.display()
        ));
    }
    if !args.manifest_dir.is_dir() {
        return Err(format!(
            "manifest dir '{}' is not a directory",
            args.manifest_dir.display()
        ));
    }

    let project_kind = detect_project_kind(&args.manifest_dir);
    if args.check {
        let checks = run_checks(&args.manifest_dir, project_kind)?;
        return Ok(InitOutcome {
            project_kind: project_kind.as_str().to_string(),
            created_files: vec![],
            skipped_files: vec![],
            checks,
        });
    }

    if project_kind == ProjectKind::DartPlugin {
        init_dart_plugin(args, project_kind)
    } else {
        init_rust_project(args, project_kind)
    }
}

fn init_dart_plugin(args: InitArgs, project_kind: ProjectKind) -> Result<InitOutcome, String> {
    let mut created_files = Vec::new();
    let mut skipped_files = Vec::new();

    let xforge_path = args.manifest_dir.join("xforge.yaml");
    let repository_default = default_repository_from_dir(&args.manifest_dir);
    let xforge_contents = format!(
        "precompiled_binaries:\n  repository: {}\n  public_key: \"<public_key_hex>\"\n  url_prefix: \"https://github.com/{}/releases/download/\"\n  mode: auto\n",
        repository_default, repository_default
    );
    write_file(
        &xforge_path,
        &xforge_contents,
        args.force,
        false,
        &mut created_files,
        &mut skipped_files,
    )?;

    let checks = run_checks(&args.manifest_dir, project_kind)?;

    Ok(InitOutcome {
        project_kind: project_kind.as_str().to_string(),
        created_files,
        skipped_files,
        checks,
    })
}

fn init_rust_project(args: InitArgs, project_kind: ProjectKind) -> Result<InitOutcome, String> {
    let mut created_files = Vec::new();
    let mut skipped_files = Vec::new();

    let rust_toolchain_path = args.manifest_dir.join("rust-toolchain.toml");
    let host_target = rustc_host_triple().unwrap_or_else(|| "x86_64-unknown-linux-gnu".to_string());
    let rust_toolchain_contents = format!(
        "[toolchain]\nchannel = \"stable\"\ntargets = [\"{}\"]\ncomponents = [\"rustfmt\", \"clippy\"]\n",
        host_target
    );
    write_file(
        &rust_toolchain_path,
        &rust_toolchain_contents,
        args.force,
        false,
        &mut created_files,
        &mut skipped_files,
    )?;

    let cargo_config_path = args.manifest_dir.join(".cargo/config.toml");
    write_file(
        &cargo_config_path,
        cargo_config_template(),
        args.force,
        false,
        &mut created_files,
        &mut skipped_files,
    )?;

    let scripts_dir = args.manifest_dir.join("scripts");
    write_file(
        &scripts_dir.join("xforge-android-linker.sh"),
        android_linker_script_template(),
        args.force,
        true,
        &mut created_files,
        &mut skipped_files,
    )?;
    write_file(
        &scripts_dir.join("xforge-link-aarch64-linux-android.sh"),
        &android_link_wrapper_template("aarch64-linux-android"),
        args.force,
        true,
        &mut created_files,
        &mut skipped_files,
    )?;
    write_file(
        &scripts_dir.join("xforge-link-armv7-linux-androideabi.sh"),
        &android_link_wrapper_template("armv7-linux-androideabi"),
        args.force,
        true,
        &mut created_files,
        &mut skipped_files,
    )?;
    write_file(
        &scripts_dir.join("xforge-link-x86_64-linux-android.sh"),
        &android_link_wrapper_template("x86_64-linux-android"),
        args.force,
        true,
        &mut created_files,
        &mut skipped_files,
    )?;

    let checks = run_checks(&args.manifest_dir, project_kind)?;

    Ok(InitOutcome {
        project_kind: project_kind.as_str().to_string(),
        created_files,
        skipped_files,
        checks,
    })
}

fn detect_project_kind(manifest_dir: &Path) -> ProjectKind {
    if manifest_dir.join("pubspec.yaml").exists() {
        ProjectKind::DartPlugin
    } else {
        ProjectKind::Rust
    }
}

fn run_checks(manifest_dir: &Path, project_kind: ProjectKind) -> Result<Vec<String>, String> {
    match project_kind {
        ProjectKind::DartPlugin => check_dart_plugin(manifest_dir),
        ProjectKind::Rust => check_rust_project(manifest_dir),
    }
}

fn check_dart_plugin(manifest_dir: &Path) -> Result<Vec<String>, String> {
    let mut checks = Vec::new();
    let config = xforge_core::config::precompiled_settings(manifest_dir)
        .map_err(|err| err.to_string())?;
    match config {
        Some(settings) => {
            checks.push("xforge.yaml: ok".to_string());
            checks.push(format!("repository: {}", settings.repository));
            checks.push("precompiled settings: ok".to_string());
        }
        None => {
            checks.push("xforge.yaml: missing precompiled_binaries".to_string());
        }
    }
    Ok(checks)
}

fn check_rust_project(manifest_dir: &Path) -> Result<Vec<String>, String> {
    let mut checks = Vec::new();

    match xforge_core::config::toolchain_settings(manifest_dir) {
        Ok(settings) => {
            checks.push("rust-toolchain.toml: ok".to_string());
            checks.push(format!("toolchain.targets: {}", settings.targets.join(",")));
        }
        Err(err) => {
            checks.push(format!("rust-toolchain.toml: {}", err));
        }
    }

    let cargo_config = manifest_dir.join(".cargo/config.toml");
    if cargo_config.exists() {
        checks.push(".cargo/config.toml: ok".to_string());
    } else {
        checks.push(".cargo/config.toml: missing".to_string());
    }

    let script_root = manifest_dir.join("scripts");
    for script in [
        "xforge-android-linker.sh",
        "xforge-link-aarch64-linux-android.sh",
        "xforge-link-armv7-linux-androideabi.sh",
        "xforge-link-x86_64-linux-android.sh",
    ] {
        let path = script_root.join(script);
        if path.exists() {
            checks.push(format!("scripts/{}: ok", script));
        } else {
            checks.push(format!("scripts/{}: missing", script));
        }
    }

    let ndk_message = match detect_android_ndk_root() {
        Some(path) => format!("android-ndk: found ({})", path.display()),
        None => "android-ndk: not found (set XFORGE_ANDROID_NDK, ANDROID_NDK_HOME, or ANDROID_SDK_ROOT)".to_string(),
    };
    checks.push(ndk_message);

    Ok(checks)
}

fn detect_android_ndk_root() -> Option<PathBuf> {
    for value in [
        std::env::var("XFORGE_ANDROID_NDK").ok(),
        std::env::var("ANDROID_NDK_HOME").ok(),
        std::env::var("ANDROID_NDK_ROOT").ok(),
    ] {
        let Some(raw) = value else {
            continue;
        };
        let path = PathBuf::from(raw);
        if path.is_dir() {
            return Some(path);
        }
    }

    if let Some(root) = std::env::var("ANDROID_SDK_ROOT")
        .ok()
        .or_else(|| std::env::var("ANDROID_HOME").ok())
    {
        if let Some(found) = latest_ndk_under(Path::new(&root).join("ndk")) {
            return Some(found);
        }
    }

    let home = std::env::var("HOME").ok()?;
    latest_ndk_under(Path::new(&home).join("Library/Android/sdk/ndk"))
        .or_else(|| latest_ndk_under(Path::new(&home).join("Android/Sdk/ndk")))
}

fn latest_ndk_under(path: PathBuf) -> Option<PathBuf> {
    let entries = fs::read_dir(&path).ok()?;
    let mut directories: Vec<PathBuf> = entries
        .flatten()
        .map(|entry| entry.path())
        .filter(|entry| entry.is_dir())
        .collect();
    directories.sort();
    directories.pop()
}

fn write_file(
    path: &Path,
    contents: &str,
    force: bool,
    executable: bool,
    created_files: &mut Vec<PathBuf>,
    skipped_files: &mut Vec<PathBuf>,
) -> Result<(), String> {
    if path.exists() && !force {
        skipped_files.push(path.to_path_buf());
        return Ok(());
    }

    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            format!(
                "failed to create directory '{}' for '{}': {}",
                parent.display(),
                path.display(),
                err
            )
        })?;
    }

    fs::write(path, contents)
        .map_err(|err| format!("failed to write '{}': {}", path.display(), err))?;

    if executable {
        set_executable(path)?;
    }

    created_files.push(path.to_path_buf());
    Ok(())
}

#[cfg(unix)]
fn set_executable(path: &Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;

    let mut permissions = fs::metadata(path)
        .map_err(|err| format!("failed to read metadata '{}': {}", path.display(), err))?
        .permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions)
        .map_err(|err| format!("failed to set executable permissions '{}': {}", path.display(), err))
}

#[cfg(not(unix))]
fn set_executable(_path: &Path) -> Result<(), String> {
    Ok(())
}

fn default_repository_from_dir(manifest_dir: &Path) -> String {
    let name = manifest_dir
        .file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("repo");
    format!("owner/{}", name)
}

fn rustc_host_triple() -> Option<String> {
    let output = std::process::Command::new("rustc").arg("-vV").output().ok()?;
    if !output.status.success() {
        return None;
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    for line in stdout.lines() {
        if let Some(triple) = line.strip_prefix("host: ") {
            return Some(triple.trim().to_string());
        }
    }
    None
}

fn cargo_config_template() -> &'static str {
    "[target.aarch64-linux-android]\nlinker = \"./scripts/xforge-link-aarch64-linux-android.sh\"\n\n[target.armv7-linux-androideabi]\nlinker = \"./scripts/xforge-link-armv7-linux-androideabi.sh\"\n\n[target.x86_64-linux-android]\nlinker = \"./scripts/xforge-link-x86_64-linux-android.sh\"\n"
}

fn android_link_wrapper_template(target: &str) -> String {
    format!(
        "#!/usr/bin/env bash\nset -euo pipefail\nscript_dir=\"$(cd -- \"$(dirname -- \"$0\")\" && pwd)\"\nexec \"$script_dir/xforge-android-linker.sh\" {} \"$@\"\n",
        target
    )
}

fn android_linker_script_template() -> &'static str {
    "#!/usr/bin/env bash\nset -euo pipefail\n\nif [[ $# -lt 1 ]]; then\n  echo \"usage: xforge-android-linker.sh <rust-target-triple> [clang args...]\" >&2\n  exit 2\nfi\n\ntarget=\"$1\"\nshift\napi=\"${XFORGE_ANDROID_API:-23}\"\n\npick_latest_ndk() {\n  local base=\"$1\"\n  if [[ ! -d \"$base\" ]]; then\n    return 1\n  fi\n  ls -1 \"$base\" 2>/dev/null | sort -V | tail -n 1\n}\n\nresolve_ndk_root() {\n  local ndk_home=\"${XFORGE_ANDROID_NDK:-${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}}\"\n  if [[ -n \"$ndk_home\" && -d \"$ndk_home\" ]]; then\n    echo \"$ndk_home\"\n    return 0\n  fi\n\n  local sdk_root=\"${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}\"\n  if [[ -n \"$sdk_root\" ]]; then\n    local latest\n    latest=\"$(pick_latest_ndk \"$sdk_root/ndk\")\" || true\n    if [[ -n \"$latest\" ]]; then\n      echo \"$sdk_root/ndk/$latest\"\n      return 0\n    fi\n  fi\n\n  local mac_sdk=\"$HOME/Library/Android/sdk\"\n  local linux_sdk=\"$HOME/Android/Sdk\"\n  local latest\n\n  latest=\"$(pick_latest_ndk \"$mac_sdk/ndk\")\" || true\n  if [[ -n \"$latest\" ]]; then\n    echo \"$mac_sdk/ndk/$latest\"\n    return 0\n  fi\n\n  latest=\"$(pick_latest_ndk \"$linux_sdk/ndk\")\" || true\n  if [[ -n \"$latest\" ]]; then\n    echo \"$linux_sdk/ndk/$latest\"\n    return 0\n  fi\n\n  echo \"unable to locate Android NDK. Set XFORGE_ANDROID_NDK, ANDROID_NDK_HOME, or ANDROID_SDK_ROOT.\" >&2\n  return 1\n}\n\nresolve_host_tag() {\n  local toolchains=\"$1/toolchains/llvm/prebuilt\"\n  local tag\n  for tag in darwin-x86_64 darwin-arm64 linux-x86_64 windows-x86_64; do\n    if [[ -d \"$toolchains/$tag/bin\" ]]; then\n      echo \"$tag\"\n      return 0\n    fi\n  done\n  echo \"unable to find NDK prebuilt host toolchain under $toolchains\" >&2\n  return 1\n}\n\nresolve_linker_binary() {\n  case \"$target\" in\n    aarch64-linux-android) echo \"aarch64-linux-android${api}-clang\" ;;\n    armv7-linux-androideabi) echo \"armv7a-linux-androideabi${api}-clang\" ;;\n    x86_64-linux-android) echo \"x86_64-linux-android${api}-clang\" ;;\n    *)\n      echo \"unsupported Android target '$target'\" >&2\n      return 1\n      ;;\n  esac\n}\n\nndk_root=\"$(resolve_ndk_root)\"\nhost_tag=\"$(resolve_host_tag \"$ndk_root\")\"\nlinker_bin=\"$(resolve_linker_binary)\"\nlinker=\"$ndk_root/toolchains/llvm/prebuilt/$host_tag/bin/$linker_bin\"\n\nif [[ ! -f \"$linker\" ]]; then\n  echo \"Android linker not found: $linker\" >&2\n  echo \"Check XFORGE_ANDROID_API (current: $api) and installed NDK version.\" >&2\n  exit 1\nfi\n\nexec \"$linker\" \"$@\"\n"
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let mut path = std::env::temp_dir();
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        path.push(format!("xforge-init-{}-{}", name, stamp));
        fs::create_dir_all(&path).expect("create temp dir");
        path
    }

    #[test]
    fn init_rust_creates_toolchain_and_linker_files() {
        let dir = temp_dir("rust");
        let outcome = run(InitArgs {
            manifest_dir: dir.clone(),
            force: false,
            check: false,
        })
        .expect("init");

        assert_eq!(outcome.project_kind, "rust");
        assert!(dir.join("rust-toolchain.toml").exists());
        assert!(dir.join(".cargo/config.toml").exists());
        assert!(dir.join("scripts/xforge-android-linker.sh").exists());
        assert!(
            fs::read_to_string(dir.join(".cargo/config.toml"))
                .expect("read config")
                .contains("xforge-link-aarch64-linux-android.sh")
        );
    }

    #[test]
    fn init_dart_plugin_creates_xforge_yaml_only() {
        let dir = temp_dir("dart");
        fs::write(dir.join("pubspec.yaml"), "name: demo_plugin\n")
            .expect("write pubspec");

        let outcome = run(InitArgs {
            manifest_dir: dir.clone(),
            force: false,
            check: false,
        })
        .expect("init");

        assert_eq!(outcome.project_kind, "dart-plugin");
        assert!(dir.join("xforge.yaml").exists());
        assert!(!dir.join("rust-toolchain.toml").exists());
    }

    #[test]
    fn init_skips_existing_files_without_force() {
        let dir = temp_dir("skip");
        fs::write(
            dir.join("rust-toolchain.toml"),
            "[toolchain]\nchannel = \"stable\"\n",
        )
        .expect("seed toolchain");

        let outcome = run(InitArgs {
            manifest_dir: dir.clone(),
            force: false,
            check: false,
        })
        .expect("init");

        assert!(
            outcome
                .skipped_files
                .iter()
                .any(|path| path.ends_with("rust-toolchain.toml"))
        );
    }

    #[test]
    fn check_mode_reports_missing_files_for_rust_project() {
        let dir = temp_dir("check-rust");
        fs::write(dir.join("Cargo.toml"), "[package]\nname = \"demo\"\nversion = \"0.1.0\"\n")
            .expect("write cargo");

        let outcome = run(InitArgs {
            manifest_dir: dir,
            force: false,
            check: true,
        })
        .expect("check");

        assert_eq!(outcome.project_kind, "rust");
        assert!(outcome.created_files.is_empty());
        assert!(outcome.checks.iter().any(|line| line.contains(".cargo/config.toml: missing")));
    }
}
