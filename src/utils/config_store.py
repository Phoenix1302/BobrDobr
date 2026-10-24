import os
import sys
import shutil
import glob
import json
import base64
import uuid
import copy
from typing import Any, Dict, List, Optional
from utils.platform_helper import is_windows
from utils.crypto_helper import encrypt_secret, decrypt_secret, is_encrypted


PROFILE_SECRET_KEYS = (
    "config_content",
    "password",
    "private_key",
    "server",
    "camouflage",
    "username",
)

AMNEZIA_REDUNDANT_KEYS = (
    "endpoint",
    "address",
    "dns",
    "allowed_ips",
    "obfuscation",
    "config_path",
)

GLOBAL_SENSITIVE_KEYS = (
    "openconnect_password",
    "openconnect_server",
    "openconnect_camouflage_secret",
    "openconnect_user",
    "amnezia_conf_path",
)


def _decrypt_profile_secrets(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Decrypts sensitive fields in-place in profile dictionary and inflates parsed memory fields."""
    for field in PROFILE_SECRET_KEYS:
        if field in profile and profile[field] and is_encrypted(str(profile[field])):
            profile[field] = decrypt_secret(str(profile[field]))

    if profile.get("proto") == "amnezia":
        content = profile.get("config_content", "")
        if content and isinstance(content, str):
            try:
                from core.amnezia import AmneziaWGLauncher
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
    return profile


def _encrypt_profile_secrets(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a copy of profile with sensitive fields securely encrypted and disk redundancy stripped."""
    p_copy = copy.deepcopy(profile)

    # For Amnezia: if config_content is missing, attempt reading from config_path if valid
    if p_copy.get("proto") == "amnezia":
        if not p_copy.get("config_content") and p_copy.get("config_path"):
            try:
                if os.path.isfile(p_copy["config_path"]):
                    with open(p_copy["config_path"], "r", encoding="utf-8", errors="ignore") as f:
                        p_copy["config_content"] = f.read().strip()
            except Exception:
                pass

    # Encrypt all sensitive fields
    for field in PROFILE_SECRET_KEYS:
        if field in p_copy and p_copy[field]:
            p_copy[field] = encrypt_secret(str(p_copy[field]))

    # For Amnezia profiles, strip redundant parameters from disk that are already sealed in config_content
    if p_copy.get("proto") == "amnezia":
        for redundant in AMNEZIA_REDUNDANT_KEYS:
            p_copy.pop(redundant, None)

    return p_copy


def is_installed_mode() -> bool:
    """Returns True if the running binary is inside %LOCALAPPDATA%/Programs/BobrDobr."""
    if not getattr(sys, "frozen", False):
        return False
    try:
        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        inst_dir = os.path.normcase(os.path.abspath(os.path.join(local_appdata, "Programs", "BobrDobr")))
        curr_exe = os.path.normcase(os.path.abspath(sys.executable))
        return curr_exe.startswith(inst_dir)
    except Exception:
        return False


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


def get_installed_config_path() -> str:
    """Returns the path to the installed version's settings.json."""
    return os.path.join(get_config_dir(), "settings.json")


def get_portable_config_path() -> str:
    """Returns the path to the portable version's settings_portable.json."""
    return os.path.join(get_config_dir(), "settings_portable.json")


def get_config_filename() -> str:
    """Returns 'settings.json' for installed mode, and 'settings_portable.json' for portable mode."""
    return "settings.json" if is_installed_mode() else "settings_portable.json"


def get_config_path() -> str:
    """
    Returns the configuration file path for the active mode.
    If running in portable mode and 'settings_portable.json' does not exist yet,
    but legacy 'settings.json' exists, automatically copies existing profiles
    so user settings are seamlessly preserved without starting from scratch.
    """
    cfg_dir = get_config_dir()
    if is_installed_mode():
        return os.path.join(cfg_dir, "settings.json")

    portable_path = os.path.join(cfg_dir, "settings_portable.json")

    # First-run graceful migration for portable version
    if not os.path.exists(portable_path):
        legacy_path = os.path.join(cfg_dir, "settings.json")
        if os.path.isfile(legacy_path):
            try:
                shutil.copy2(legacy_path, portable_path)
            except Exception:
                pass

    return portable_path


class ConfigStore:
    """
    Manages persistent user preferences, multiple connection profiles,
    in-memory VPN configs, and credentials between launcher restarts.
    """

    def __init__(self):
        self.file_path = get_config_path()
        self._is_cleared = False
        self._needs_save = False
        self.data: Dict[str, Any] = self._load()
        self._ensure_profiles()
        self._migrate_amnezia_profiles()
        self._prune_backups()
        if self._needs_save:
            self.save()

    def _prune_backups(self) -> None:
        """Prunes old settings backups, keeping only the 3 most recent files."""
        try:
            backup_dir = os.path.join(get_config_dir(), "backups")
            if os.path.isdir(backup_dir):
                backup_files = [
                    os.path.join(backup_dir, f)
                    for f in os.listdir(backup_dir)
                    if f.startswith("settings_pre_upgrade_") and f.endswith(".json")
                ]
                backup_files.sort(key=os.path.getmtime)
                while len(backup_files) > 3:
                    old_bk = backup_files.pop(0)
                    try:
                        os.remove(old_bk)
                    except Exception:
                        pass
        except Exception:
            pass

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

        needs_save = False

        # Decrypt profiles in memory & detect whether disk format needs hardening
        profiles = data.get("profiles", [])
        if isinstance(profiles, list):
            for p in profiles:
                if isinstance(p, dict):
                    proto = p.get("proto")
                    if proto == "amnezia":
                        for red in AMNEZIA_REDUNDANT_KEYS:
                            if red in p:
                                needs_save = True
                                break
                        if "config_content" in p and p["config_content"] and not is_encrypted(str(p["config_content"])):
                            needs_save = True
                    elif proto == "openconnect":
                        for field in ("server", "camouflage", "username", "password"):
                            if field in p and p[field] and not is_encrypted(str(p[field])):
                                needs_save = True
                                break

                    _decrypt_profile_secrets(p)

        # Decrypt global sensitive fields
        for key in GLOBAL_SENSITIVE_KEYS:
            if key in data and data[key]:
                val = str(data[key])
                if is_encrypted(val):
                    data[key] = decrypt_secret(val)
                else:
                    needs_save = True
                    if key == "openconnect_password":
                        try:
                            data["openconnect_password"] = base64.b64decode(val.encode("utf-8")).decode("utf-8")
                        except Exception:
                            pass

        self._needs_save = needs_save
        return data

    def save(self) -> None:
        if self._is_cleared:
            return
        try:
            from utils.version import APP_VERSION

            # Create a protected copy for saving to disk
            disk_data = copy.deepcopy(self.data)
            disk_data["version"] = APP_VERSION

            profiles = disk_data.get("profiles", [])
            if isinstance(profiles, list):
                disk_data["profiles"] = [_encrypt_profile_secrets(p) for p in profiles if isinstance(p, dict)]

            for key in GLOBAL_SENSITIVE_KEYS:
                if key in disk_data and disk_data[key]:
                    disk_data[key] = encrypt_secret(str(disk_data[key]))

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(disk_data, f, indent=2, ensure_ascii=False)
            self._needs_save = False
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
