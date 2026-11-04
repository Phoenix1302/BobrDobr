"""
AmneziaWG and WireGuard configuration file parser.
Provides utility functions to parse .conf strings and extract interface,
peer, and obfuscation parameters without importing core VPN engine modules.
"""

from typing import Dict, Any, List

OBFUSCATION_KEYS: List[str] = ["Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"]


def parse_amnezia_config_text(content: str) -> Dict[str, Any]:
    """
    Parses AmneziaWG .conf string content, extracting interface, peer,
    obfuscation parameters and shortcut gateway/IP fields.
    """
    parsed_data: Dict[str, Any] = {
        "interface": {},
        "peer": {},
        "obfuscation": {},
        "endpoint": "",
        "address": "",
        "dns": "",
        "allowed_ips": ""
    }

    current_section = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip().lower()
            continue

        if "=" in line and current_section:
            key, val = [p.strip() for p in line.split("=", 1)]
            if current_section == "interface":
                if key in OBFUSCATION_KEYS:
                    parsed_data["obfuscation"][key] = val
                else:
                    parsed_data["interface"][key] = val
            elif current_section == "peer":
                parsed_data["peer"][key] = val

    parsed_data["endpoint"] = parsed_data["peer"].get("Endpoint", "")
    parsed_data["address"] = parsed_data["interface"].get("Address", "")
    parsed_data["dns"] = parsed_data["interface"].get("DNS", "")
    parsed_data["allowed_ips"] = parsed_data["peer"].get("AllowedIPs", "")

    return parsed_data
