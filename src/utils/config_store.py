import os
import glob
import json
import base64
import uuid
import copy
from typing import Any, Dict, List, Optional
from utils.platform_helper import is_windows
from utils.crypto_helper import encrypt_secret, decrypt_secret, is_encrypted


def _decrypt_profile_secrets(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Decrypts sensitive fields in-place in profile dictionary."""
    if "config_content" in profile and is_encrypted(profile["config_content"]):
        profile["config_content"] = decrypt_secret(profile["config_content"])
    if "password" in profile and is_encrypted(profile["password"]):
        profile["password"] = decrypt_secret(profile["password"])
    if "private_key" in profile and is_encrypted(profile["private_key"]):
        profile["private_key"] = decrypt_secret(profile["private_key"])
    return profile


def _encrypt_profile_secrets(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a copy of profile with sensitive fields securely encrypted."""
    p_copy = copy.deepcopy(profile)
    if "config_content" in p_copy and p_copy["config_content"]:
        p_copy["config_content"] = encrypt_secret(p_copy["config_content"])
    if "password" in p_copy and p_copy["password"]:
        p_copy["password"] = encrypt_secret(p_copy["password"])
    if "private_key" in p_copy and p_copy["private_key"]:
        p_copy["private_key"] = encrypt_secret(p_copy["private_key"])
    return p_copy


def get_config_dir() -> str:
    """Returns the persistent configuration directory for BobrDobr VPN."""
    if is_windows():
        appdata = os.environ.get("APPDATA")
        if appdata:
            base = os.path.join(appdata, "BobrDobr")
        else:
            base = os.path.expanduser("~/.bobrdobr")
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            base = os.path.join(xdg_config, "bobrdobr")
        else:
            base = os.path.expanduser("~/.config/bobrdobr")

    os.makedirs(base, exist_ok=True)
    return base


def get_config_path() -> str:
    return os.path.join(get_config_dir(), "settings.json")


class ConfigStore:
    """
    Manages persistent user preferences, multiple connection profiles,
    in-memory VPN configs, and credentials between launcher restarts.
    """

    def __init__(self):
        self.file_path = get_config_path()
        self._is_cleared = False
        self.data: Dict[str, Any] = self._load()
        self._ensure_profiles()
        self._migrate_amnezia_profiles()

    def _load(self) -> Dict[str, Any]:
        data = {}
        if os.path.isfile(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        if not isinstance(data, dict):
            data = {}

        # Decrypt profiles in memory
        profiles = data.get("profiles", [])
        if isinstance(profiles, list):
            for p in profiles:
                if isinstance(p, dict):
                    _decrypt_profile_secrets(p)

        # Decrypt global openconnect_password
        if "openconnect_password" in data:
            val = data["openconnect_password"]
            if is_encrypted(val):
                data["openconnect_password"] = decrypt_secret(val)
            else:
                try:
                    data["openconnect_password"] = base64.b64decode(val.encode("utf-8")).decode("utf-8")
                except Exception:
                    pass

        return data

    def save(self) -> None:
        if self._is_cleared:
            return
        try:
            # Create a protected copy for saving to disk
            disk_data = copy.deepcopy(self.data)
            profiles = disk_data.get("profiles", [])
            if isinstance(profiles, list):
                disk_data["profiles"] = [_encrypt_profile_secrets(p) for p in profiles if isinstance(p, dict)]

            if "openconnect_password" in disk_data and disk_data["openconnect_password"]:
                disk_data["openconnect_password"] = encrypt_secret(disk_data["openconnect_password"])

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(disk_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def clear(self) -> None:
        """Purges in-memory configuration and deletes settings.json from disk."""
        self._is_cleared = True
        self.data = {"profiles": []}
        if os.path.isfile(self.file_path):
            try:
                os.remove(self.file_path)
            except Exception:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if self._is_cleared:
            return
        self.data[key] = value
        self.save()

    def _ensure_profiles(self) -> None:
        """Ensures the profiles list is initialized as a list (starts completely empty, no fake profiles)."""
        profiles = self.data.get("profiles")
        if not isinstance(profiles, list):
            self.data["profiles"] = []

    def _migrate_amnezia_profiles(self) -> None:
        """
        Ensures existing AmneziaWG profiles store config_content inside settings.json
        if they originally only pointed to a local .conf file on disk.
        Does NOT sniff temporary directories (%TEMP%).
        """
        from core.amnezia import AmneziaWGLauncher

        profiles = self.get_profiles()
        modified = False

        for p in profiles:
            if p.get("proto") == "amnezia":
                content = p.get("config_content", "").strip()

                # If config_content is empty, only try reading from a valid user config_path
                if not content:
                    cfg_path = p.get("config_path", "")
                    if cfg_path and os.path.isfile(cfg_path):
                        try:
                            with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read().strip()
                        except Exception:
                            content = ""

                # If content was found from user's file, parse parameters and persist
                if content:
                    p["config_content"] = content
                    try:
                        parsed = AmneziaWGLauncher.parse_config_text(content)
                        if parsed.get("endpoint"):
                            p["endpoint"] = parsed["endpoint"]
                        if parsed.get("address"):
                            p["address"] = parsed["address"]
                        if parsed.get("dns"):
                            p["dns"] = parsed["dns"]
                        if parsed.get("allowed_ips"):
                            p["allowed_ips"] = parsed["allowed_ips"]
                        if parsed.get("obfuscation"):
                            p["obfuscation"] = parsed["obfuscation"]
                    except Exception:
                        pass
                    modified = True

        if modified:
            self.data["profiles"] = profiles
            self.save()

    def get_profiles(self) -> List[Dict[str, Any]]:
        return self.data.get("profiles", [])

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        for p in self.get_profiles():
            if p.get("id") == profile_id:
                return p
        return None

    def save_profile(self, profile: Dict[str, Any]) -> str:
        """Adds or updates a connection profile with full parameter persistence."""
        from core.amnezia import AmneziaWGLauncher

        # If AmneziaWG, ensure config_content is parsed and preserved
        if profile.get("proto") == "amnezia":
            content = profile.get("config_content", "").strip()
            cfg_path = profile.get("config_path", "")

            if not content and cfg_path and os.path.isfile(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read().strip()
                        profile["config_content"] = content
                except Exception:
                    pass

            if content:
                try:
                    parsed = AmneziaWGLauncher.parse_config_text(content)
                    if parsed.get("endpoint"):
                        profile["endpoint"] = parsed["endpoint"]
                    if parsed.get("address"):
                        profile["address"] = parsed["address"]
                    if parsed.get("dns"):
                        profile["dns"] = parsed["dns"]
                    if parsed.get("allowed_ips"):
                        profile["allowed_ips"] = parsed["allowed_ips"]
                    if parsed.get("obfuscation"):
                        profile["obfuscation"] = parsed["obfuscation"]
                except Exception:
                    pass

        profiles = self.get_profiles()
        p_id = profile.get("id")
        if not p_id:
            p_id = str(uuid.uuid4())
            profile["id"] = p_id
            profiles.append(profile)
        else:
            updated = False
            for i, existing in enumerate(profiles):
                if existing.get("id") == p_id:
                    profiles[i] = profile
                    updated = True
                    break
            if not updated:
                profiles.append(profile)

        self.data["profiles"] = profiles
        self.save()
        return p_id

    def delete_profile(self, profile_id: str) -> bool:
        """Removes a profile by ID."""
        profiles = self.get_profiles()
        initial_len = len(profiles)
        profiles = [p for p in profiles if p.get("id") != profile_id]
        if len(profiles) != initial_len:
            self.data["profiles"] = profiles
            self.save()
            return True
        return False

    def get_password(self, key: str = "openconnect_password") -> str:
        """Retrieves password securely from local settings."""
        val = self.data.get(key, "")
        if not val:
            return ""
        if is_encrypted(val):
            return decrypt_secret(val)
        return val

    def set_password(self, password: str, key: str = "openconnect_password") -> None:
        """Stores password securely in user settings."""
        if password:
            self.data[key] = password
        else:
            self.data.pop(key, None)
        self.save()


# Singleton instance
settings = ConfigStore()
