use std::fmt;
use std::str::FromStr;

use crate::bindings::BindingLanguage;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum PlatformKey {
    LinuxX86_64,
    LinuxAarch64,
    MacosArm64,
    MacosX86_64,
    IosArm64,
    IosSimulatorArm64,
    IosSimulatorX86_64,
    AndroidArm64,
    AndroidArmv7,
    AndroidX86,
    AndroidX86_64,
    WindowsX86_64Msvc,
    WindowsArm64Msvc,
}

impl PlatformKey {
    pub fn from_rust_target(triple: &str) -> Vec<Self> {
        platforms_for_rust_target(triple)
    }

    pub fn as_str(self) -> &'static str {
        self.descriptor().key_str
    }

    pub fn rust_targets(self) -> &'static [&'static str] {
        self.descriptor().rust_targets
    }

    pub fn packaging(self) -> PackagingSupport {
        self.descriptor().packaging
    }

    pub fn bindings(self) -> BindingSupport {
        self.descriptor().bindings
    }

    pub fn descriptor(self) -> &'static PlatformDescriptor {
        registry()
            .iter()
            .find(|entry| entry.key == self)
            .expect("platform key missing from registry")
    }
}

impl fmt::Display for PlatformKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for PlatformKey {
    type Err = PlatformKeyError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        if !is_valid_platform_key_format(value) {
            return Err(PlatformKeyError::InvalidFormat);
        }
        registry()
            .iter()
            .find(|entry| entry.key_str == value)
            .map(|entry| entry.key)
            .ok_or_else(|| PlatformKeyError::UnknownKey(value.to_string()))
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum PackagingFormat {
    TarGz,
    Zip,
    Xcframework,
    SharedObject,
    Dylib,
    Dll,
}

impl fmt::Display for PackagingFormat {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let value = match self {
            PackagingFormat::TarGz => "tar.gz",
            PackagingFormat::Zip => "zip",
            PackagingFormat::Xcframework => "xcframework",
            PackagingFormat::SharedObject => "so",
            PackagingFormat::Dylib => "dylib",
            PackagingFormat::Dll => "dll",
        };
        f.write_str(value)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PackagingSupport {
    Known(&'static [PackagingFormat]),
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BindingSupport {
    Known(&'static [BindingLanguage]),
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SupportStatus {
    Supported,
    Unsupported,
    Unknown,
}

pub struct PlatformDescriptor {
    pub key: PlatformKey,
    pub key_str: &'static str,
    pub rust_targets: &'static [&'static str],
    pub packaging: PackagingSupport,
    pub bindings: BindingSupport,
}

const SUPPORTED_BINDINGS: &[BindingLanguage] = &[
    BindingLanguage::Dart,
    BindingLanguage::Kotlin,
    BindingLanguage::Python,
    BindingLanguage::Swift,
];

const ANDROID_RUST_TARGETS_ARM64: &[&str] = &["aarch64-linux-android"];
const ANDROID_RUST_TARGETS_ARMV7: &[&str] = &["armv7-linux-androideabi"];
const ANDROID_RUST_TARGETS_X86: &[&str] = &["i686-linux-android"];
const ANDROID_RUST_TARGETS_X86_64: &[&str] = &["x86_64-linux-android"];
const IOS_RUST_TARGETS_DEVICE: &[&str] = &["aarch64-apple-ios"];
const IOS_RUST_TARGETS_SIMULATOR_ARM64: &[&str] = &["aarch64-apple-ios-sim"];
const IOS_RUST_TARGETS_SIMULATOR_X86_64: &[&str] = &["x86_64-apple-ios"];
const LINUX_RUST_TARGETS_X86_64: &[&str] = &["x86_64-unknown-linux-gnu"];
const LINUX_RUST_TARGETS_AARCH64: &[&str] = &["aarch64-unknown-linux-gnu"];
const MACOS_RUST_TARGETS_ARM64: &[&str] = &["aarch64-apple-darwin"];
const MACOS_RUST_TARGETS_X86_64: &[&str] = &["x86_64-apple-darwin"];
const WINDOWS_RUST_TARGETS_X86_64_MSVC: &[&str] = &["x86_64-pc-windows-msvc"];
const WINDOWS_RUST_TARGETS_ARM64_MSVC: &[&str] = &["aarch64-pc-windows-msvc"];

const DEFAULT_LINUX_PACKAGING: PackagingSupport =
    PackagingSupport::Known(&[PackagingFormat::SharedObject, PackagingFormat::TarGz]);
const DEFAULT_ANDROID_PACKAGING: PackagingSupport =
    PackagingSupport::Known(&[PackagingFormat::SharedObject, PackagingFormat::TarGz]);
const DEFAULT_WINDOWS_PACKAGING: PackagingSupport =
    PackagingSupport::Known(&[PackagingFormat::Dll, PackagingFormat::Zip]);
const DEFAULT_APPLE_PACKAGING: PackagingSupport = PackagingSupport::Known(&[
    PackagingFormat::Dylib,
    PackagingFormat::Zip,
    PackagingFormat::Xcframework,
]);

const DEFAULT_BINDINGS: BindingSupport = BindingSupport::Known(SUPPORTED_BINDINGS);

static PLATFORM_REGISTRY: &[PlatformDescriptor] = &[
    PlatformDescriptor {
        key: PlatformKey::LinuxX86_64,
        key_str: "x86_64-unknown-linux-gnu",
        rust_targets: LINUX_RUST_TARGETS_X86_64,
        packaging: DEFAULT_LINUX_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::LinuxAarch64,
        key_str: "aarch64-unknown-linux-gnu",
        rust_targets: LINUX_RUST_TARGETS_AARCH64,
        packaging: DEFAULT_LINUX_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::MacosArm64,
        key_str: "aarch64-apple-darwin",
        rust_targets: MACOS_RUST_TARGETS_ARM64,
        packaging: DEFAULT_APPLE_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::MacosX86_64,
        key_str: "x86_64-apple-darwin",
        rust_targets: MACOS_RUST_TARGETS_X86_64,
        packaging: DEFAULT_APPLE_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::IosArm64,
        key_str: "aarch64-apple-ios",
        rust_targets: IOS_RUST_TARGETS_DEVICE,
        packaging: DEFAULT_APPLE_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::IosSimulatorArm64,
        key_str: "aarch64-apple-ios-sim",
        rust_targets: IOS_RUST_TARGETS_SIMULATOR_ARM64,
        packaging: DEFAULT_APPLE_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::IosSimulatorX86_64,
        key_str: "x86_64-apple-ios",
        rust_targets: IOS_RUST_TARGETS_SIMULATOR_X86_64,
        packaging: DEFAULT_APPLE_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::AndroidArm64,
        key_str: "aarch64-linux-android",
        rust_targets: ANDROID_RUST_TARGETS_ARM64,
        packaging: DEFAULT_ANDROID_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::AndroidArmv7,
        key_str: "armv7-linux-androideabi",
        rust_targets: ANDROID_RUST_TARGETS_ARMV7,
        packaging: DEFAULT_ANDROID_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::AndroidX86,
        key_str: "i686-linux-android",
        rust_targets: ANDROID_RUST_TARGETS_X86,
        packaging: DEFAULT_ANDROID_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::AndroidX86_64,
        key_str: "x86_64-linux-android",
        rust_targets: ANDROID_RUST_TARGETS_X86_64,
        packaging: DEFAULT_ANDROID_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::WindowsX86_64Msvc,
        key_str: "x86_64-pc-windows-msvc",
        rust_targets: WINDOWS_RUST_TARGETS_X86_64_MSVC,
        packaging: DEFAULT_WINDOWS_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
    PlatformDescriptor {
        key: PlatformKey::WindowsArm64Msvc,
        key_str: "aarch64-pc-windows-msvc",
        rust_targets: WINDOWS_RUST_TARGETS_ARM64_MSVC,
        packaging: DEFAULT_WINDOWS_PACKAGING,
        bindings: DEFAULT_BINDINGS,
    },
];

pub fn registry() -> &'static [PlatformDescriptor] {
    PLATFORM_REGISTRY
}

pub fn all_platform_keys() -> Vec<PlatformKey> {
    registry().iter().map(|entry| entry.key).collect()
}

pub fn platforms_for_rust_target(triple: &str) -> Vec<PlatformKey> {
    registry()
        .iter()
        .filter(|entry| entry.rust_targets.iter().any(|target| *target == triple))
        .map(|entry| entry.key)
        .collect()
}

pub fn all_rust_targets() -> Vec<&'static str> {
    let mut targets = Vec::new();
    for entry in registry() {
        for target in entry.rust_targets {
            if !targets.contains(target) {
                targets.push(*target);
            }
        }
    }
    targets
}

pub fn is_supported_rust_target(triple: &str) -> bool {
    registry()
        .iter()
        .any(|entry| entry.rust_targets.iter().any(|target| *target == triple))
}

pub fn binding_support(platform: PlatformKey, binding: &str) -> SupportStatus {
    let binding = match BindingLanguage::from_str(binding) {
        Ok(binding) => binding,
        Err(_) => return SupportStatus::Unknown,
    };
    match platform.bindings() {
        BindingSupport::Known(entries) => {
            if entries.iter().any(|item| *item == binding) {
                SupportStatus::Supported
            } else {
                SupportStatus::Unsupported
            }
        }
        BindingSupport::Unknown => SupportStatus::Unknown,
    }
}

pub fn packaging_support(platform: PlatformKey, packaging: PackagingFormat) -> SupportStatus {
    match platform.packaging() {
        PackagingSupport::Known(entries) => {
            if entries.iter().any(|item| *item == packaging) {
                SupportStatus::Supported
            } else {
                SupportStatus::Unsupported
            }
        }
        PackagingSupport::Unknown => SupportStatus::Unknown,
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PlatformKeyError {
    InvalidFormat,
    UnknownKey(String),
}

impl fmt::Display for PlatformKeyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PlatformKeyError::InvalidFormat => {
                write!(f, "target triple must be lowercase and hyphenated")
            }
            PlatformKeyError::UnknownKey(value) => {
                write!(f, "unknown target triple '{}'", value)
            }
        }
    }
}

impl std::error::Error for PlatformKeyError {}

fn is_valid_platform_key_format(value: &str) -> bool {
    if !value.contains('-') {
        return false;
    }
    value
        .chars()
        .all(|ch| ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == '-' || ch == '_')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn platform_key_round_trips() {
        let key = PlatformKey::LinuxX86_64;
        let encoded = key.to_string();
        let decoded: PlatformKey = encoded.parse().expect("should parse");
        assert_eq!(decoded, key);
    }

    #[test]
    fn rust_target_maps_to_key() {
        let keys = PlatformKey::from_rust_target("aarch64-apple-ios");
        assert_eq!(keys, vec![PlatformKey::IosArm64]);
    }

    #[test]
    fn invalid_key_rejected() {
        let result: Result<PlatformKey, _> = "linux".parse();
        assert!(matches!(result, Err(PlatformKeyError::InvalidFormat)));
    }

    #[test]
    fn unknown_key_rejected() {
        let result: Result<PlatformKey, _> = "linux-arm64".parse();
        assert!(matches!(result, Err(PlatformKeyError::UnknownKey(_))));
    }

    #[test]
    fn binding_support_known() {
        let status = binding_support(PlatformKey::LinuxX86_64, "dart");
        assert_eq!(status, SupportStatus::Supported);
    }

    #[test]
    fn packaging_support_known() {
        let status = packaging_support(PlatformKey::LinuxX86_64, PackagingFormat::TarGz);
        assert_eq!(status, SupportStatus::Supported);
    }
}
