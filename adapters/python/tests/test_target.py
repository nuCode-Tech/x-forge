import sys
from unittest.mock import patch

import pytest

from xforge.precompiled.target import detect_host_target_triple


def test_detect_host_returns_triple():
    triple = detect_host_target_triple()
    assert isinstance(triple, str)
    assert "-" in triple
    assert triple in (
        "x86_64-apple-darwin",
        "aarch64-apple-darwin",
        "x86_64-unknown-linux-gnu",
        "aarch64-unknown-linux-gnu",
        "x86_64-pc-windows-msvc",
        "aarch64-pc-windows-msvc",
    ) or triple.endswith("-darwin") or triple.endswith("-linux-gnu") or triple.endswith("-msvc")


def test_detect_host_linux_x64():
    with patch("sys.platform", "linux"), patch("platform.machine", return_value="x86_64"):
        assert detect_host_target_triple() == "x86_64-unknown-linux-gnu"


def test_detect_host_darwin_arm64():
    with patch("sys.platform", "darwin"), patch("platform.machine", return_value="arm64"):
        assert detect_host_target_triple() == "aarch64-apple-darwin"
