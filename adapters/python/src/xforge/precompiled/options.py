"""
Parse xforge.yaml precompiled_binaries: repository, public_key, url_prefix, mode.
"""
import re
from enum import Enum
from pathlib import Path

import yaml

from xforge.precompiled.util import decode_hex


class PrecompiledBinaryMode(Enum):
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


def _parse_mode(raw: str) -> PrecompiledBinaryMode:
    v = raw.strip().lower()
    if v == "auto":
        return PrecompiledBinaryMode.AUTO
    if v in ("always", "download"):
        return PrecompiledBinaryMode.ALWAYS
    if v in ("never", "build", "off", "disabled"):
        return PrecompiledBinaryMode.NEVER
    raise ValueError(
        "precompiled_binaries.mode must be one of: auto, always, never "
        "(aliases: download->always, build->never)"
    )


def _normalize_owner_repo(raw: str) -> str | None:
    v = re.sub(r"^https?://", "", raw.strip())
    v = re.sub(r"^github\.com/", "", v)
    v = v.rstrip("/")
    parts = v.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}"


class PrecompiledBinariesConfig:
    def __init__(
        self,
        *,
        repository: str,
        public_key: bytes,
        url_prefix: str | None = None,
        mode: PrecompiledBinaryMode = PrecompiledBinaryMode.AUTO,
    ):
        self.repository = repository
        self.public_key = public_key
        self.url_prefix = url_prefix
        self.mode = mode

    def file_url(self, build_id: str, file_name: str) -> str:
        if self.url_prefix and self.url_prefix.strip():
            base = self.url_prefix.rstrip("/")
            return f"{base}/{build_id}/{file_name}"
        return f"https://github.com/{self.repository}/releases/download/{build_id}/{file_name}"


class XforgeOptions:
    def __init__(self, *, precompiled_binaries: PrecompiledBinariesConfig | None):
        self.precompiled_binaries = precompiled_binaries

    @staticmethod
    def load(crate_dir: str | Path) -> "XforgeOptions":
        crate_dir = Path(crate_dir)
        path = crate_dir / "xforge.yaml"
        if not path.is_file():
            return XforgeOptions(precompiled_binaries=None)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("xforge.yaml must be a map")
        node = data.get("precompiled_binaries")
        if node is None:
            return XforgeOptions(precompiled_binaries=None)
        if not isinstance(node, dict):
            raise ValueError("precompiled_binaries must be a map")

        url_prefix = node.get("url_prefix")
        if url_prefix is not None and not isinstance(url_prefix, str):
            raise ValueError("precompiled_binaries.url_prefix must be a string")

        mode = PrecompiledBinaryMode.AUTO
        mode_node = node.get("mode")
        if mode_node is not None:
            if not isinstance(mode_node, str):
                raise ValueError("precompiled_binaries.mode must be a string")
            mode = _parse_mode(mode_node)

        repo_node = node.get("repository")
        if repo_node is None or not isinstance(repo_node, str):
            raise ValueError("precompiled_binaries.repository must be a string")
        repository = _normalize_owner_repo(repo_node)
        if repository is None:
            raise ValueError(
                "precompiled_binaries.repository must be in owner/repo format "
                "(or github.com/owner/repo)"
            )

        pk_node = node.get("public_key")
        if pk_node is None or not isinstance(pk_node, str):
            raise ValueError("precompiled_binaries.public_key must be a string")
        key_bytes = decode_hex(pk_node)
        if len(key_bytes) != 32:
            raise ValueError("public_key must be 32 bytes")

        return XforgeOptions(
            precompiled_binaries=PrecompiledBinariesConfig(
                repository=repository,
                public_key=key_bytes,
                url_prefix=url_prefix,
                mode=mode,
            )
        )
