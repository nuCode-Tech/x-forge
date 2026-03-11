"""
Fetch and verify manifest + artifacts; cache under .xforge in crate dir.
Manifest JSON uses camelCase (platforms.targets, name, triples, artifacts).
"""
import json
from dataclasses import dataclass
from pathlib import Path

from xforge.options import PrecompiledBinariesConfig, PrecompiledBinaryMode
from xforge.util import read_or_download_bytes, verify_ed25519_signature, write_bytes_atomically

_MANIFEST_FILE_NAME = "xforge-manifest.json"


class ManifestSignatureException(Exception):
    pass


class ArtifactSignatureException(Exception):
    pass


class PlatformNotFoundException(Exception):
    pass


class ArtifactNotFoundException(Exception):
    pass


@dataclass
class ManifestPlatform:
    name: str
    triples: list[str]
    artifacts: list[str]

    def matches_target(self, target: str) -> bool:
        return self.name == target or target in self.triples


@dataclass
class XforgeManifest:
    platforms: list[ManifestPlatform]


@dataclass
class ArtifactSelection:
    platform: ManifestPlatform
    artifact_name: str


@dataclass
class ArtifactResolution:
    downloaded: bool
    artifact: Path | None = None
    reason: str | None = None

    @staticmethod
    def downloaded_result(artifact: Path) -> "ArtifactResolution":
        return ArtifactResolution(downloaded=True, artifact=artifact)

    @staticmethod
    def fallback_result(reason: str) -> "ArtifactResolution":
        return ArtifactResolution(downloaded=False, reason=reason)


def _parse_manifest(json_string: str) -> XforgeManifest:
    raw = json.loads(json_string)
    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a JSON object.")
    platforms_node = raw.get("platforms")
    if not isinstance(platforms_node, dict):
        raise ValueError("Manifest platforms must be a map.")
    targets_node = platforms_node.get("targets")
    if not isinstance(targets_node, list):
        raise ValueError("Manifest platforms.targets must be a list.")
    platforms = []
    for entry in targets_node:
        if not isinstance(entry, dict):
            raise ValueError("Manifest platform entry must be a map.")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Manifest platform.name must be a string.")
        triples = _string_list_or_empty(entry.get("triples"))
        artifacts = _string_list_or_empty(entry.get("artifacts"))
        platforms.append(
            ManifestPlatform(name=name, triples=triples, artifacts=artifacts)
        )
    return XforgeManifest(platforms=platforms)


def _string_list_or_empty(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("Expected a list of strings.")
    return [str(x).strip() for x in raw if isinstance(x, str) and x.strip()]


def _delete_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink(missing_ok=True)


class PrecompiledArtifactsProvider:
    def __init__(self, *, crate_dir: str | Path, config: PrecompiledBinariesConfig):
        self.crate_dir = Path(crate_dir)
        self.config = config

    @property
    def _cache_root(self) -> Path:
        return self.crate_dir / ".xforge"

    def _manifest_cache_dir(self, build_id: str) -> Path:
        return self._cache_root / "manifests" / build_id

    def _artifact_cache_dir(self, build_id: str) -> Path:
        return self._cache_root / "artifacts" / build_id

    def fetch_verified_manifest(self, build_id: str) -> XforgeManifest:
        manifest_dir = self._manifest_cache_dir(build_id)
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = manifest_dir / _MANIFEST_FILE_NAME
        manifest_sig = manifest_dir / f"{_MANIFEST_FILE_NAME}.sig"

        manifest_url = self.config.file_url(build_id, _MANIFEST_FILE_NAME)
        sig_url = self.config.file_url(build_id, f"{_MANIFEST_FILE_NAME}.sig")

        manifest_bytes = read_or_download_bytes(manifest_file, manifest_url)
        sig_bytes = read_or_download_bytes(manifest_sig, sig_url)

        if not verify_ed25519_signature(
            public_key=self.config.public_key,
            message=manifest_bytes,
            signature=sig_bytes,
        ):
            _delete_if_exists(manifest_file)
            _delete_if_exists(manifest_sig)
            raise ManifestSignatureException("Manifest signature verification failed.")

        return _parse_manifest(manifest_bytes.decode("utf-8"))

    def select_artifact(
        self, *, manifest: XforgeManifest, target: str
    ) -> ArtifactSelection:
        for platform in manifest.platforms:
            if platform.matches_target(target):
                if not platform.artifacts:
                    raise ArtifactNotFoundException(
                        f'Manifest platform "{platform.name}" has no artifacts.'
                    )
                return ArtifactSelection(
                    platform=platform,
                    artifact_name=platform.artifacts[0],
                )
        raise PlatformNotFoundException(
            f'No platform match for target "{target}" in manifest.'
        )

    def fetch_verified_artifact(
        self, *, build_id: str, artifact_name: str
    ) -> Path:
        artifact_dir = self._artifact_cache_dir(build_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_file = artifact_dir / artifact_name
        sig_file = artifact_dir / f"{artifact_name}.sig"

        artifact_url = self.config.file_url(build_id, artifact_name)
        sig_url = self.config.file_url(build_id, f"{artifact_name}.sig")

        artifact_bytes = read_or_download_bytes(artifact_file, artifact_url)
        sig_bytes = read_or_download_bytes(sig_file, sig_url)

        if not verify_ed25519_signature(
            public_key=self.config.public_key,
            message=artifact_bytes,
            signature=sig_bytes,
        ):
            _delete_if_exists(artifact_file)
            _delete_if_exists(sig_file)
            raise ArtifactSignatureException(
                "Artifact signature verification failed."
            )

        return artifact_file

    def resolve_artifact(
        self,
        *,
        build_id: str,
        target: str,
        mode: PrecompiledBinaryMode,
        rust_available: bool,
    ) -> ArtifactResolution:
        manifest = self.fetch_verified_manifest(build_id)

        try:
            selection = self.select_artifact(manifest=manifest, target=target)
        except (PlatformNotFoundException, ArtifactNotFoundException) as e:
            return self._fallback_or_throw(str(e), mode, rust_available)

        try:
            artifact_path = self.fetch_verified_artifact(
                build_id=build_id,
                artifact_name=selection.artifact_name,
            )
            return ArtifactResolution.downloaded_result(artifact_path)
        except ArtifactSignatureException as e:
            return self._fallback_or_throw(str(e), mode, rust_available)

    def _fallback_or_throw(
        self,
        reason: str,
        mode: PrecompiledBinaryMode,
        rust_available: bool,
    ) -> ArtifactResolution:
        if mode == PrecompiledBinaryMode.ALWAYS:
            raise RuntimeError(
                f"Precompiled binaries are required (mode=always). {reason}"
            )
        if rust_available:
            return ArtifactResolution.fallback_result(
                f"{reason} Falling back to local build."
            )
        raise RuntimeError(
            f"{reason} Rust toolchain not detected; cannot fall back to local build."
        )
