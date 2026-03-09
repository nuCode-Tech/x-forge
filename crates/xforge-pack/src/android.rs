use std::fs;
use std::path::{Path, PathBuf};

use xforge_core::platform::PlatformKey;

use crate::common::{derive_package_name, entries_from_dir, replace_extension, write_zip};
use crate::{PackError, PackExecutor, PackFormat, PackRequest, PackResult};

pub struct AarPacker;

impl PackExecutor for AarPacker {
    fn pack(&self, request: &PackRequest) -> Result<PackResult, PackError> {
        if request.format != PackFormat::AAR {
            return Err(PackError::InvalidRequest {
                message: "aar packer only supports PackFormat::AAR".to_string(),
            });
        }
        if request.inputs.is_empty() {
            return Err(PackError::InvalidRequest {
                message: "aar packer expects at least one input".to_string(),
            });
        }
        let first = &request.inputs[0];
        let temp = tempfile::tempdir().map_err(|err| PackError::Io {
            message: err.to_string(),
        })?;
        let root = temp.path();
        create_classes_jar(root)?;
        let package_name = android_package_name(&first.artifact)?;
        write_android_manifest(root, &package_name)?;
        write_metadata(root, &first.layout, &first.artifact)?;
        write_jni_libs(root, &request.inputs)?;
        let entries = entries_from_dir(root)?;
        let mut output_dir = PathBuf::from(&request.output_dir);
        fs::create_dir_all(&output_dir).map_err(|err| PackError::Io {
            message: err.to_string(),
        })?;
        let output_name = replace_extension(&first.artifact.artifact_name, "aar");
        output_dir.push(output_name);
        write_zip(&output_dir, &entries)?;
        Ok(PackResult {
            format: PackFormat::AAR,
            output_paths: vec![output_dir.to_string_lossy().into_owned()],
        })
    }
}

fn write_jni_libs(root: &Path, inputs: &[crate::PackInput]) -> Result<(), PackError> {
    let jni_root = root.join("jni");
    fs::create_dir_all(&jni_root).map_err(|err| PackError::Io {
        message: err.to_string(),
    })?;
    for input in inputs {
        let abi = android_abi(input.artifact.platform)?;
        let abi_dir = jni_root.join(abi);
        fs::create_dir_all(&abi_dir).map_err(|err| PackError::Io {
            message: err.to_string(),
        })?;
        let library_path = PathBuf::from(&input.artifact.library_path);
        let filename = library_path
            .file_name()
            .ok_or_else(|| PackError::InvalidRequest {
                message: "android library path missing filename".to_string(),
            })?;
        let destination = abi_dir.join(filename);
        if destination.exists() {
            return Err(PackError::InvalidRequest {
                message: format!("duplicate abi entry '{}'", abi),
            });
        }
        fs::copy(&library_path, &destination).map_err(|err| PackError::Io {
            message: err.to_string(),
        })?;
    }
    Ok(())
}

fn write_metadata(
    root: &Path,
    layout: &xforge_core::artifact::layout::ArchiveLayout,
    artifact: &xforge_core::build_plan::BuiltArtifact,
) -> Result<(), PackError> {
    let manifest_path = root.join(&layout.manifest_path);
    if let Some(parent) = manifest_path.parent() {
        fs::create_dir_all(parent).map_err(|err| PackError::Io {
            message: err.to_string(),
        })?;
    }
    fs::copy(&artifact.manifest_path, &manifest_path).map_err(|err| PackError::Io {
        message: err.to_string(),
    })?;
    let build_id_path = root.join(&layout.build_id_path);
    if let Some(parent) = build_id_path.parent() {
        fs::create_dir_all(parent).map_err(|err| PackError::Io {
            message: err.to_string(),
        })?;
    }
    fs::copy(&artifact.build_id_path, &build_id_path).map_err(|err| PackError::Io {
        message: err.to_string(),
    })?;
    Ok(())
}

fn write_android_manifest(root: &Path, package_name: &str) -> Result<(), PackError> {
    let contents = format!(
        "<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\" package=\"{}\"></manifest>",
        package_name
    );
    fs::write(root.join("AndroidManifest.xml"), contents).map_err(|err| PackError::Io {
        message: err.to_string(),
    })?;
    Ok(())
}

fn android_package_name(
    artifact: &xforge_core::build_plan::BuiltArtifact,
) -> Result<String, PackError> {
    let derived = derive_package_name(artifact);
    if is_valid_android_package(&derived) {
        return Ok(derived);
    }
    Err(PackError::InvalidRequest {
        message: format!(
            "invalid android package name '{}' derived from artifact_name",
            derived
        ),
    })
}

fn is_valid_android_package(name: &str) -> bool {
    if name.is_empty() {
        return false;
    }
    let mut segments = name.split('.');
    let first = match segments.next() {
        Some(value) => value,
        None => return false,
    };
    if !is_valid_java_identifier(first) {
        return false;
    }
    for segment in segments {
        if !is_valid_java_identifier(segment) {
            return false;
        }
    }
    true
}

fn is_valid_java_identifier(segment: &str) -> bool {
    let mut chars = segment.chars();
    let first = match chars.next() {
        Some(value) => value,
        None => return false,
    };
    if !(first.is_ascii_alphabetic() || first == '_') {
        return false;
    }
    chars.all(|ch| ch.is_ascii_alphanumeric() || ch == '_')
}

fn create_classes_jar(root: &Path) -> Result<(), PackError> {
    let jar_path = root.join("classes.jar");
    let file = fs::File::create(&jar_path).map_err(|err| PackError::Io {
        message: err.to_string(),
    })?;
    let writer = zip::ZipWriter::new(file);
    writer.finish().map_err(|err| PackError::Io {
        message: err.to_string(),
    })?;
    Ok(())
}

fn android_abi(platform: PlatformKey) -> Result<&'static str, PackError> {
    match platform {
        PlatformKey::AndroidArm64 => Ok("arm64-v8a"),
        PlatformKey::AndroidArmv7 => Ok("armeabi-v7a"),
        PlatformKey::AndroidX86 => Ok("x86"),
        PlatformKey::AndroidX86_64 => Ok("x86_64"),
        _ => Err(PackError::InvalidRequest {
            message: format!("non-android platform '{}'", platform),
        }),
    }
}
