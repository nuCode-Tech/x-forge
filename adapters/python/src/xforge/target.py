"""
Detect host Rust target triple (e.g. aarch64-apple-darwin, x86_64-unknown-linux-gnu).
"""
import platform
import sys


def detect_host_target_triple() -> str:
    machine = platform.machine().lower()
    system = sys.platform

    arch = "x86_64"
    if "aarch64" in machine or "arm64" in machine:
        arch = "aarch64"
    elif "x86_64" in machine or "amd64" in machine or "x64" in machine:
        arch = "x86_64"
    elif "i686" in machine or "i386" in machine or "x86" in machine:
        arch = "x86"
    elif "arm" in machine:
        arch = "arm"

    if system == "darwin":
        return f"{arch}-apple-darwin"
    if system == "linux":
        return f"{arch}-unknown-linux-gnu"
    if system == "win32":
        return f"{arch}-pc-windows-msvc"
    # Fallback
    return "x86_64-unknown-linux-gnu"
