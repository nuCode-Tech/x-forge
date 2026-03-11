import json
import pytest

from xforge.precompiled.artifacts_provider import (
    ArtifactNotFoundException,
    PlatformNotFoundException,
    _parse_manifest,
    ManifestPlatform,
    XforgeManifest,
)


def test_parse_manifest_camelCase():
    # Manifest from xforge bundle uses camelCase
    raw = {
        "schemaVersion": "xforge.manifest.v1",
        "platforms": {
            "default": "x86_64-unknown-linux-gnu",
            "targets": [
                {
                    "name": "x86_64-unknown-linux-gnu",
                    "buildId": "b1-abc",
                    "triples": ["x86_64-unknown-linux-gnu"],
                    "artifacts": ["pkg-0.1.0-x86_64-unknown-linux-gnu.tar.gz"],
                },
            ],
        },
    }
    manifest = _parse_manifest(json.dumps(raw))
    assert len(manifest.platforms) == 1
    p = manifest.platforms[0]
    assert p.name == "x86_64-unknown-linux-gnu"
    assert p.matches_target("x86_64-unknown-linux-gnu")
    assert p.artifacts[0] == "pkg-0.1.0-x86_64-unknown-linux-gnu.tar.gz"


def test_select_artifact_platform_not_found():
    manifest = XforgeManifest(
        platforms=[
            ManifestPlatform(
                name="x86_64-unknown-linux-gnu",
                triples=[],
                artifacts=["foo.tar.gz"],
            ),
        ]
    )
    from xforge.precompiled.artifacts_provider import PrecompiledArtifactsProvider
    from xforge.precompiled.options import PrecompiledBinariesConfig
    from xforge.precompiled.util import decode_hex

    config = PrecompiledBinariesConfig(
        repository="a/b",
        public_key=decode_hex("0" * 64),
    )
    provider = PrecompiledArtifactsProvider(crate_dir="/tmp", config=config)
    with pytest.raises(PlatformNotFoundException, match="aarch64-apple-darwin"):
        provider.select_artifact(manifest=manifest, target="aarch64-apple-darwin")
