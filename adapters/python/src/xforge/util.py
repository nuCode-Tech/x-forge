"""
Hex encode/decode, HTTP with retry, atomic write, Ed25519 verify.
"""
import os
import time
from pathlib import Path

import requests
from nacl.encoding import RawEncoder
from nacl.signing import VerifyKey

def decode_hex(hex_str: str) -> bytes:
    normalized = hex_str.strip().lower()
    if len(normalized) % 2 != 0:
        raise ValueError("Invalid hex length")
    return bytes.fromhex(normalized)


def hex_encode(data: bytes) -> str:
    return data.hex()


def http_get_with_retry(
    url: str,
    *,
    headers: dict | None = None,
    max_attempts: int = 4,
    timeout: float = 30.0,
    retry_delay: float = 1.0,
) -> requests.Response:
    for attempt in range(1, max_attempts + 1):
        try:
            return requests.get(url, headers=headers or {}, timeout=timeout)
        except (requests.RequestException, requests.Timeout):
            if attempt == max_attempts:
                raise
            time.sleep(retry_delay)
    raise RuntimeError("Unreachable")


def write_bytes_atomically(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{time.time_ns()}.tmp")
    tmp.write_bytes(data)
    try:
        tmp.replace(path)
    except OSError:
        if path.exists():
            path.unlink()
        tmp.replace(path)


def read_or_download_bytes(
    path: Path,
    url: str,
    *,
    headers: dict | None = None,
) -> bytes:
    if path.is_file():
        return path.read_bytes()
    response = http_get_with_retry(url, headers=headers)
    response.raise_for_status()
    data = response.content
    write_bytes_atomically(path, data)
    return data


def verify_ed25519_signature(
    *,
    public_key: bytes,
    message: bytes,
    signature: bytes,
) -> bool:
    if len(public_key) != 32:
        raise ValueError("public_key must be 32 bytes")
    try:
        key = VerifyKey(public_key, encoder=RawEncoder)
        # PyNaCl verify() expects signed_message = signature + message
        key.verify(signature + message)
        return True
    except Exception:
        return False
