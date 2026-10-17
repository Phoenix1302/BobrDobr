"""GitHub Update Checker for BobrDobr VPN Launcher."""
import json
import re
import ssl
import urllib.request
from typing import Dict, Any, Optional

from PySide6.QtCore import QThread, Signal
from utils.version import APP_VERSION, GITHUB_REPO


def parse_version(v_str: str) -> tuple:
    """Parses version string into integer tuple (e.g. 'v1.0.8' -> (1, 0, 8))."""
    nums = re.findall(r"\d+", str(v_str))
    return tuple(int(x) for x in nums) if nums else (0,)


def is_newer_version(remote_ver: str, current_ver: str) -> bool:
    """Returns True if remote_ver is strictly newer than current_ver."""
    return parse_version(remote_ver) > parse_version(current_ver)


def _fetch_github_json(url: str, headers: dict, timeout: int = 6) -> Optional[Any]:
    """
    Fetches and parses JSON from GitHub API with resilient SSL verification fallback.
    Gracefully handles Windows certificate store quirks, missing root certificates,
    and third-party antivirus SSL/TLS inspection without throwing errors.
    """
    req = urllib.request.Request(url, headers=headers)

    # 1. Try standard verified SSL context (optionally with certifi if installed)
    try:
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()

        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e_standard:
        err_msg = str(e_standard).lower()
        # If failure is related to SSL/TLS certificate verification on Windows,
        # fallback to unverified context to tolerate antivirus inspection or missing roots.
        if "certificate" in err_msg or "ssl" in err_msg or "verify failed" in err_msg or "handshake" in err_msg:
            try:
                ctx_unverified = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=timeout, context=ctx_unverified) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e_fallback:
                raise e_fallback
        raise e_standard


def check_github_update(
    repo: str = GITHUB_REPO,
    current_version: str = APP_VERSION,
    timeout: int = 6
) -> Dict[str, Any]:
    """
    Queries GitHub API to determine if a newer release or tag is available.
    Returns a dictionary with status, latest version, URLs, and notes.
    """
    result = {
        "update_available": False,
        "latest_version": "",
        "current_version": current_version,
        "release_name": "",
        "release_url": f"https://github.com/{repo}/releases",
        "download_url": "",
        "body": "",
        "published_at": "",
        "error": None,
    }
    headers = {
        "User-Agent": "BobrDobr-VPN-Client",
        "Accept": "application/vnd.github.v3+json",
    }

    # 1. Try /releases/latest first
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        data = _fetch_github_json(url, headers, timeout=timeout)
        if data and isinstance(data, dict):
            tag = data.get("tag_name", "")
            raw_ver = tag.lstrip("vV")
            result["latest_version"] = raw_ver
            result["release_name"] = data.get("name") or f"БобрДобр v{raw_ver}"
            result["release_url"] = data.get("html_url") or f"https://github.com/{repo}/releases/tag/{tag}"
            result["body"] = data.get("body", "")
            result["published_at"] = data.get("published_at", "")

            # Look for Windows executable asset
            for asset in data.get("assets", []):
                asset_name = asset.get("name", "").lower()
                if asset_name.endswith(".exe"):
                    result["download_url"] = asset.get("browser_download_url", "")
                    break

            if is_newer_version(raw_ver, current_version):
                result["update_available"] = True
            return result
    except Exception as e_rel:
        # 2. Fallback to /tags if /releases/latest failed or returned 404
        try:
            url_tags = f"https://api.github.com/repos/{repo}/tags"
            tags = _fetch_github_json(url_tags, headers, timeout=timeout)
            if tags and isinstance(tags, list):
                latest_tag = tags[0].get("name", "")
                raw_ver = latest_tag.lstrip("vV")
                result["latest_version"] = raw_ver
                result["release_name"] = f"БобрДобр v{raw_ver}"
                result["release_url"] = f"https://github.com/{repo}/releases/tag/{latest_tag}"
                if is_newer_version(raw_ver, current_version):
                    result["update_available"] = True
                return result
        except Exception as e_tags:
            result["error"] = str(e_tags)
            return result

        result["error"] = str(e_rel)
        return result


class GitHubUpdateCheckerThread(QThread):
    """Asynchronous worker for non-blocking GitHub update checks."""
    result_ready = Signal(dict)

    def __init__(
        self,
        repo: str = GITHUB_REPO,
        current_version: str = APP_VERSION,
        timeout: int = 6,
        parent=None
    ):
        super().__init__(parent)
        self.repo = repo
        self.current_version = current_version
        self.timeout = timeout

    def run(self):
        res = check_github_update(
            repo=self.repo,
            current_version=self.current_version,
            timeout=self.timeout
        )
        self.result_ready.emit(res)
