import sys
import os
import base64
import hashlib
import hmac
from typing import Optional

DPAPI_PREFIX = "dpapi:"
FALLBACK_PREFIX = "enc:v1:"

# Optional Windows DPAPI imports
if sys.platform.startswith("win"):
    import ctypes
    import ctypes.wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte))
        ]


def _dpapi_protect(data: bytes) -> Optional[bytes]:
    """Encrypts bytes using Windows DPAPI (CryptProtectData). Bound to current user."""
    if not sys.platform.startswith("win"):
        return None
    try:
        p_in = _DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
        p_out = _DATA_BLOB()
        res = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(p_in),
            "BobrDobrProtectedSecret",
            None,
            None,
            None,
            0,
            ctypes.byref(p_out)
        )
        if res:
            buf = (ctypes.c_byte * p_out.cbData)()
            ctypes.memmove(buf, p_out.pbData, p_out.cbData)
            ctypes.windll.kernel32.LocalFree(p_out.pbData)
            return bytes(buf)
    except Exception:
        pass
    return None


def _dpapi_unprotect(data: bytes) -> Optional[bytes]:
    """
    Decrypts bytes using Windows DPAPI (CryptUnprotectData).
    Fails safely and returns None if file was stolen or copied to another machine/account.
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        p_in = _DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
        p_out = _DATA_BLOB()
        res = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(p_in),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(p_out)
        )
        if res:
            buf = (ctypes.c_byte * p_out.cbData)()
            ctypes.memmove(buf, p_out.pbData, p_out.cbData)
            ctypes.windll.kernel32.LocalFree(p_out.pbData)
            return bytes(buf)
    except Exception:
        pass
    return None


def _get_machine_seed() -> bytes:
    """Returns a machine and user bound seed for fallback encryption."""
    env_parts = [
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERNAME", ""),
        os.environ.get("USER", ""),
        os.environ.get("HOSTNAME", ""),
        "BobrDobr_Salt_SecKey_2026"
    ]
    return "|".join(env_parts).encode("utf-8")


def _fallback_encrypt(data: bytes) -> bytes:
    """Fallback machine-bound stream cipher with HMAC integrity check."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", _get_machine_seed(), salt, 10000, 32)
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(data):
        keystream.extend(hashlib.sha256(key + counter.to_bytes(4, "big")).digest())
        counter += 1
    cipher = bytes(a ^ b for a, b in zip(data, keystream[:len(data)]))
    tag = hmac.new(key, salt + cipher, hashlib.sha256).digest()[:16]
    return salt + tag + cipher


def _fallback_decrypt(data: bytes) -> Optional[bytes]:
    """Decrypts fallback machine-bound cipher, checking HMAC integrity."""
    if len(data) < 32:
        return None
    salt = data[:16]
    tag = data[16:32]
    cipher = data[32:]
    key = hashlib.pbkdf2_hmac("sha256", _get_machine_seed(), salt, 10000, 32)
    expected_tag = hmac.new(key, salt + cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expected_tag):
        return None
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(cipher):
        keystream.extend(hashlib.sha256(key + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(a ^ b for a, b in zip(cipher, keystream[:len(cipher)]))


def encrypt_secret(text: str) -> str:
    """
    Encrypts a sensitive string (password, private key, configuration).
    On Windows, uses Windows DPAPI (CryptProtectData).
    If stolen to another machine, decryption is impossible.
    """
    if not text:
        return ""
    raw = text.encode("utf-8")
    dpapi_res = _dpapi_protect(raw)
    if dpapi_res is not None:
        return DPAPI_PREFIX + base64.b64encode(dpapi_res).decode("ascii")

    fallback_res = _fallback_encrypt(raw)
    return FALLBACK_PREFIX + base64.b64encode(fallback_res).decode("ascii")


def decrypt_secret(val: str) -> str:
    """
    Decrypts a sensitive string previously encrypted with encrypt_secret().
    If the value is unencrypted legacy plaintext, returns it as-is.
    If decryption fails (e.g. file was stolen to another machine), returns empty string.
    """
    if not val or not isinstance(val, str):
        return ""

    if val.startswith(DPAPI_PREFIX):
        try:
            raw = base64.b64decode(val[len(DPAPI_PREFIX):].encode("ascii"))
            dec = _dpapi_unprotect(raw)
            if dec is not None:
                return dec.decode("utf-8", errors="replace")
        except Exception:
            pass
        return ""

    if val.startswith(FALLBACK_PREFIX):
        try:
            raw = base64.b64decode(val[len(FALLBACK_PREFIX):].encode("ascii"))
            dec = _fallback_decrypt(raw)
            if dec is not None:
                return dec.decode("utf-8", errors="replace")
        except Exception:
            pass
        return ""

    # Legacy or plaintext
    return val


def is_encrypted(val: str) -> bool:
    """Checks if a string is encrypted with BobrDobr secure storage."""
    if not isinstance(val, str):
        return False
    return val.startswith(DPAPI_PREFIX) or val.startswith(FALLBACK_PREFIX)
