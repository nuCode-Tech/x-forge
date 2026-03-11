"""
xforge — Python adapter for XForge precompiled binaries.

Exposes get_library_path, load_native_library, PrecompiledResolver, and helpers
for computing build_id and loading xforge.yaml config.
"""
from xforge.precompiled.artifacts_provider import (
    ArtifactNotFoundException,
    ArtifactResolution,
    ArtifactSignatureException,
    ManifestSignatureException,
    PlatformNotFoundException,
    PrecompiledArtifactsProvider,
)
from xforge.precompiled.crate_hash import compute_release_hash
from xforge.precompiled.options import PrecompiledBinaryMode, XforgeOptions
from xforge.precompiled.resolver import (
    get_library_path,
    load_native_library,
    PrecompiledResolver,
)
from xforge.precompiled.loader import load_or_raise
from xforge.precompiled.target import detect_host_target_triple

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
    "load_or_raise",
]
