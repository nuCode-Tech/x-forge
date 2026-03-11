"""
xforge — Python adapter for XForge precompiled binaries.

Exposes get_library_path, load_native_library, PrecompiledResolver, and helpers
for computing build_id and loading xforge.yaml config.
"""
from xforge.artifacts_provider import (
    ArtifactNotFoundException,
    ArtifactResolution,
    ArtifactSignatureException,
    ManifestSignatureException,
    PlatformNotFoundException,
    PrecompiledArtifactsProvider,
)
from xforge.crate_hash import compute_release_hash
from xforge.options import PrecompiledBinaryMode, XforgeOptions
from xforge.resolver import (
    get_library_path,
    load_native_library,
    PrecompiledResolver,
)
from xforge.target import detect_host_target_triple

__all__ = [
    "ArtifactNotFoundException",
    "ArtifactResolution",
    "ArtifactSignatureException",
    "ManifestSignatureException",
    "PlatformNotFoundException",
    "PrecompiledArtifactsProvider",
    "PrecompiledBinaryMode",
    "PrecompiledResolver",
    "XforgeOptions",
    "compute_release_hash",
    "detect_host_target_triple",
    "get_library_path",
    "load_native_library",
]
