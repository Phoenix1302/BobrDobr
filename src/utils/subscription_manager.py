"""
Subscription Manager module for BobrDobr VPN.
Handles fetching subscription profiles from remote BobrDobr VPN subscription servers,
converting server connection schemas into local AmneziaWG and OpenConnect profiles,
synchronizing profiles, caching metadata, and managing lifecycle.
"""

import os
import re
import ssl
import time
import uuid
import json
import socket
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any, Optional

import urllib.request
import urllib.error
import urllib.parse

from utils.conf_parser import parse_amnezia_config_text


class SubscriptionError(Exception):
    """Исключение, возникающее при ошибках загрузки, валидации или обработки подписки."""
    def __init__(self, message: str, status: Optional[str] = None):
        super().__init__(message)
        self.status = status


def normalize_subscription_url(url: str) -> str:
    """
    Нормализует URL подписки: очищает пробелы и гарантирует протокол https://.
    Формат ссылок: https://{host}/api/v1/sub/{TOKEN} или https://{host}/sub/{TOKEN}.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        raise SubscriptionError("URL подписки не указан.")

    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        cleaned = f"https://{cleaned}"

    return cleaned


def format_subscription_profile_name(name: str) -> str:
    """
    Добавляет суффикс '-sub' (в нижнем регистре, слитно без пробела) к имени профиля подписки,
    удаляя любые существующие варианты суффикса (' -SUB', '-SUB', ' -sub', '-sub', ' - Sub' и т.д.).
    Если имя пустое, возвращает 'vpn-sub'.
    Примеры:
        'Egor_awg1' -> 'Egor_awg1-sub'
        'Egor_awg1 -SUB' -> 'Egor_awg1-sub'
        'Egor_awg1-SUB' -> 'Egor_awg1-sub'
        'Egor_awg1 -sub' -> 'Egor_awg1-sub'
        'Egor_awg1-sub' -> 'Egor_awg1-sub'
        'Egor_awg1 - Sub' -> 'Egor_awg1-sub'
        '' -> 'vpn-sub'
    """
    stripped = (name or "").strip()
    if not stripped:
        return "vpn-sub"

    # Удаляем любые существующие варианты суффикса (с дефисом и любыми пробелами вокруг него, без учета регистра)
    base_name = re.sub(r'(?i)(?:\s*-\s*sub)+$', '', stripped).strip()
    if not base_name:
        return "vpn-sub"
    return f"{base_name}-sub"


def get_cabinet_url(url: str = "") -> str:
    """
    Извлекает корневой домен сайта подписки для перехода в Личный Кабинет.
    - Принимает ссылку на подписку (если пустая — читает сохраненную ссылку из settings или кэша).
    - Использует urllib.parse.urlsplit.
    - Корректно извлекает схему и домен: https://persona.netphoenix.ru/api/v1/sub/TOKEN -> https://persona.netphoenix.ru
    - Если в кэше данных подписки есть поле cabinet_url или dashboard_url, возвращает его с приоритетом.
    - Если ссылка не задана или некорректна, возвращает пустую строку.
    """
    raw_url = (url or "").strip()

    # Если URL не передан явно, проверяем кэш и сохранённые настройки
    if not raw_url:
        try:
            from utils.config_store import settings
            cache = settings.get("subscription_cache") or {}
            if isinstance(cache, dict):
                cache_url = cache.get("cabinet_url") or cache.get("dashboard_url")
                if not cache_url and isinstance(cache.get("server"), dict):
                    cache_url = cache["server"].get("cabinet_url") or cache["server"].get("dashboard_url")
                if cache_url and str(cache_url).strip():
                    return str(cache_url).strip().rstrip("/")

            saved_cabinet = (settings.get("subscription_cabinet_url") or "").strip()
            if saved_cabinet:
                return saved_cabinet.rstrip("/")

            raw_url = (settings.get("subscription_url") or "").strip()

            # Если ссылка подписки не настроена в настройках, но есть подписные профили,
            # извлекаем хост/домен (например, из bobr.netphoenix.ru) для перехода в ЛК
            if not raw_url:
                profiles = [
                    p for p in settings.get_profiles()
                    if p.get("is_subscription") or p.get("sub_id") is not None or str(p.get("name", "")).lower().endswith("-sub")
                ]
                for p in profiles:
                    sub_url = (p.get("subscription_url") or p.get("cabinet_url") or p.get("url") or "").strip()
                    if sub_url:
                        raw_url = sub_url
                        break
                    srv = (p.get("server") or p.get("server_host") or p.get("host") or "").strip()
                    if not srv and p.get("endpoint"):
                        srv = str(p.get("endpoint")).strip().split(":")[0].strip()
                    if srv:
                        clean_srv = re.sub(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', '', srv).split('/')[0].split(':')[0].strip()
                        if clean_srv and not clean_srv.startswith("127.") and not clean_srv.startswith("10.") and not clean_srv.startswith("192.168."):
                            raw_url = f"https://{clean_srv}"
                            break
        except Exception:
            pass

    if not raw_url:
        return ""

    # Если переданный URL не содержит схемы, добавляем https://
    candidate = raw_url
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', candidate):
        candidate = f"https://{candidate}"

    try:
        parsed = urllib.parse.urlsplit(candidate)
        if not parsed.hostname or " " in parsed.netloc or not re.match(r'^[a-zA-Z0-9.-]+$', parsed.hostname):
            return ""

        scheme = parsed.scheme.lower() or "https"
        return f"{scheme}://{parsed.netloc}".rstrip("/")
    except Exception:
        return ""


def fetch_subscription(url: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Выполняет HTTPS GET запрос к серверу подписки BobrDobr VPN с нужными заголовками,
    поддержкой экспоненциального отката при HTTP 429 и детальной обработкой ошибок.

    :param url: URL подписки вида https://{host}/api/v1/sub/{TOKEN}
    :param timeout: таймаут сетевого запроса в секундах
    :return: распарсенный словарь ответа сервера
    :raises SubscriptionError: с понятным человекочитаемым сообщением на русском языке
    """
    target_url = normalize_subscription_url(url)

    req = urllib.request.Request(
        target_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "BobrDobr-VPN/1.1.0"
        },
        method="GET"
    )

    # Настройка SSL контекста с системным или certifi хранилищем доверенных сертификатов
    ssl_context = ssl.create_default_context()
    try:
        import certifi
        ssl_context.load_verify_locations(certifi.where())
    except Exception:
        pass

    # Экспоненциальный откат для HTTP 429 (Too Many Requests)
    max_retries = 3
    retry_delays = [1.0, 2.0, 4.0]

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
                status_code = resp.getcode()
                userinfo_header = resp.headers.get("Subscription-Userinfo", "")
                raw_body = resp.read().decode("utf-8")

                try:
                    data = json.loads(raw_body)
                except Exception:
                    raise SubscriptionError("Некорректный ответ от сервера подписки.")

                if not isinstance(data, dict):
                    raise SubscriptionError("Некорректный формат ответа от сервера подписки.")

                # Проверка статуса подписки в теле ответа
                body_status = str(data.get("status", "")).strip().lower()
                if body_status in ("blocked", "banned"):
                    raise SubscriptionError("Доступ заблокирован администратором.", status="blocked")
                if body_status == "expired":
                    raise SubscriptionError("Срок действия подписки истек. Продлите доступ в личном кабинете.", status="expired")

                # Извлечение метрик и срока действия из заголовка Subscription-Userinfo
                if userinfo_header:
                    expire_match = re.search(r"expire=(\d+)", userinfo_header)
                    if expire_match:
                        try:
                            exp_ts = int(expire_match.group(1))
                            if "user" not in data or not isinstance(data["user"], dict):
                                data["user"] = {}
                            if not data["user"].get("expires_at"):
                                exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
                                data["user"]["expires_at"] = exp_dt.strftime("%Y-%m-%dT%H:%M:%S")
                            data["_expire_timestamp"] = exp_ts
                        except Exception:
                            pass

                # Сохранение URL личного кабинета из ответа сервера или извлечение из ссылки подписки
                cabinet_url = ""
                if isinstance(data, dict):
                    cabinet_url = str(data.get("cabinet_url") or data.get("dashboard_url") or "").strip()
                    if not cabinet_url and isinstance(data.get("server"), dict):
                        cabinet_url = str(data["server"].get("cabinet_url") or data["server"].get("dashboard_url") or "").strip()

                if not cabinet_url:
                    cabinet_url = get_cabinet_url(target_url)

                if cabinet_url:
                    if "cabinet_url" not in data:
                        data["cabinet_url"] = cabinet_url
                    try:
                        from utils.config_store import settings
                        settings.data["subscription_cabinet_url"] = cabinet_url
                        settings.save()
                    except Exception:
                        pass

                return data

        except urllib.error.HTTPError as e:
            if e.code == 429:
                if attempt < max_retries:
                    retry_after = e.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        sleep_time = min(float(retry_after), 10.0)
                    else:
                        sleep_time = retry_delays[attempt]
                    time.sleep(sleep_time)
                    continue
                else:
                    raise SubscriptionError(
                        "Превышен лимит запросов к серверу подписок. Пожалуйста, подождите минуту перед повторной попыткой."
                    )

            # Чтение тела ошибки
            err_body = ""
            err_message = ""
            try:
                err_body = e.read().decode("utf-8", errors="ignore")
                err_json = json.loads(err_body)
                if isinstance(err_json, dict):
                    err_message = str(err_json.get("error", ""))
            except Exception:
                err_message = err_body

            search_text = f"{err_message} {err_body}".lower()

            if e.code == 401:
                raise SubscriptionError(
                    "Токен подписки недействителен или был отозван. Получите новую ссылку в личном кабинете."
                )
            elif e.code == 403:
                if "block" in search_text or "заблокирован" in search_text:
                    raise SubscriptionError("Доступ заблокирован администратором.", status="blocked")
                elif "expire" in search_text or "истек" in search_text or "истёк" in search_text:
                    raise SubscriptionError("Срок действия подписки истек. Продлите доступ в личном кабинете.", status="expired")
                else:
                    raise SubscriptionError("Доступ к подписке запрещен. Проверьте статус в личном кабинете.", status="blocked")
            elif e.code == 404:
                raise SubscriptionError("Сервер подписки или профиль не найден (404). Проверьте правильность ссылки.")
            elif 500 <= e.code < 600:
                raise SubscriptionError(f"Ошибка на сервере подписки (код {e.code}). Попробуйте позже.")
            else:
                msg = err_message or f"код {e.code}"
                raise SubscriptionError(f"Ошибка сервера подписки: {msg}")

        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError, OSError):
            raise SubscriptionError("Не удалось подключиться к серверу подписки. Проверьте интернет-соединение.")


def convert_connection_to_profile(conn: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Преобразует объект подключения из ответа сервера в профиль BobrDobr VPN.
    Поддерживает протоколы:
      - 'awg' -> BobrDobr AmneziaWG ('amnezia')
      - 'ocserv' -> BobrDobr OpenConnect ('openconnect')
    """
    if not isinstance(conn, dict):
        return None

    raw_proto = str(conn.get("proto", "")).strip().lower()
    raw_name = str(conn.get("name", "")).strip()
    profile_name = format_subscription_profile_name(raw_name or f"Sub_Profile_{conn.get('id', '')}")

    # 1. Протокол AmneziaWG
    if raw_proto in ("awg", "amnezia"):
        config_text = conn.get("config_text") or conn.get("config_content") or ""
        profile: Dict[str, Any] = {
            "name": profile_name,
            "proto": "amnezia",
            "is_subscription": True,
            "sub_id": conn.get("id"),
            "config_content": config_text,
            "interface": "bobr0",
            "mode": conn.get("mode", "split"),
        }

        # Опциональные вспомогательные поля, если предоставлены сервером
        if "ip" in conn:
            profile["address"] = str(conn["ip"])
        if "endpoint" in conn:
            profile["endpoint"] = str(conn["endpoint"])
        if "dns" in conn:
            profile["dns"] = str(conn["dns"])
        if "allowed_ips" in conn:
            profile["allowed_ips"] = str(conn["allowed_ips"])
        if "obfuscation" in conn and isinstance(conn["obfuscation"], dict):
            profile["obfuscation"] = conn["obfuscation"]

        # Если в config_content передан текст конфигурации WireGuard/AmneziaWG, парсим его
        if profile["config_content"]:
            try:
                parsed = parse_amnezia_config_text(profile["config_content"])
                for field in ("endpoint", "address", "dns", "allowed_ips", "obfuscation"):
                    if parsed.get(field) and not profile.get(field):
                        profile[field] = parsed[field]
            except Exception:
                pass

        return profile

    # 2. Протокол OpenConnect (ocserv)
    elif raw_proto in ("ocserv", "openconnect"):
        server_host = str(conn.get("host") or conn.get("server") or "").strip()
        port = int(conn.get("port", 443))
        username = str(conn.get("username", "")).strip()
        password = str(conn.get("password", ""))
        group = str(conn.get("group", "split")).strip()
        mode = str(conn.get("mode", "split")).strip()
        uri = str(conn.get("uri", "")).strip()

        profile = {
            "name": profile_name,
            "proto": "openconnect",
            "protocol": "anyconnect",
            "is_subscription": True,
            "sub_id": conn.get("id"),
            "server": server_host,
            "port": port,
            "username": username,
            "password": password,
            "group": group,
            "remember_password": True,
            "mode": mode,
        }

        if uri:
            profile["uri"] = uri

        # Обработка параметров маскировки (Camouflage)
        # В ocserv / AnyConnect камуфляж строго передается через query-string: https://host:port/?secret
        cam = conn.get("camouflage")
        if isinstance(cam, dict) and cam.get("enabled"):
            secret = str(cam.get("secret", "")).strip().lstrip("/?")
            path = str(cam.get("path", "")).strip()

            if secret:
                profile["camouflage"] = secret
                if "?" not in server_host:
                    profile["server"] = f"{server_host}/?{secret}"
                profile["camouflage_connect_url"] = f"https://{server_host}:{port}/?{secret}"
            elif cam.get("connect_url"):
                profile["camouflage_connect_url"] = str(cam.get("connect_url", "")).strip()

            if path:
                profile["camouflage_path"] = path
            if "tls_sni" in cam:
                profile["camouflage_tls_sni"] = str(cam["tls_sni"])
            if "dtls" in cam:
                profile["camouflage_dtls"] = bool(cam["dtls"])

        return profile

    return None


def sync_subscription(url: str = "") -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Синхронизирует профили подписки:
      1. Запрашивает актуальный список подключений с сервера подписки.
      2. Сохраняет существующие ручные профили пользователя без изменений.
      3. Обновляет существующие профили подписки по sub_id или добавляет новые.
      4. Удаляет локальные профили подписки, удалённые на сервере.
      5. Сохраняет зашифрованный URL подписки, метаданные и сырой кэш в настройках.

    :param url: URL ссылки на подписку (если пустой, используется сохранённый subscription_url)
    :return: Кортеж (успех: bool, сообщение: str, список_обновлённых_профилей: List[dict])
    """
    from utils.config_store import settings

    target_url = (url or "").strip()
    if not target_url:
        target_url = (settings.get("subscription_url") or "").strip()

    if not target_url:
        return (False, "URL подписки не указан.", [])

    # 1. Загрузка данных с сервера
    try:
        data = fetch_subscription(target_url)
    except SubscriptionError as se:
        # Если сервер вернул информацию о блокировке или окончании срока действия,
        # фиксируем статус в настройках для активации эффекта заморозки и баннеров
        if se.status:
            settings.data["subscription_status"] = se.status
            settings.save()
        else:
            err_lower = str(se).lower()
            if "заблокирован" in err_lower or "block" in err_lower:
                settings.data["subscription_status"] = "blocked"
                settings.save()
            elif "истек" in err_lower or "истёк" in err_lower or "expire" in err_lower:
                settings.data["subscription_status"] = "expired"
                settings.save()
        return (False, str(se), [])
    except Exception as e:
        return (False, f"Не удалось обновить подписку: {e}", [])

    connections = data.get("connections", [])
    if not isinstance(connections, list):
        return (False, "Сервер подписки не предоставил список подключений.", [])

    # 2. Разделение существующих профилей на ручные и подписные
    existing_profiles = settings.get_profiles()
    manual_profiles: List[Dict[str, Any]] = []
    sub_profiles_by_sub_id: Dict[Any, Dict[str, Any]] = {}

    for p in existing_profiles:
        if p.get("is_subscription") or p.get("sub_id") is not None:
            s_id = p.get("sub_id")
            if s_id is not None:
                sub_profiles_by_sub_id[s_id] = p
        else:
            manual_profiles.append(p)

    # 3. Конвертация новых подключений и обновление
    updated_sub_profiles: List[Dict[str, Any]] = []
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        profile = convert_connection_to_profile(conn)
        if not profile:
            continue

        s_id = profile.get("sub_id")
        if s_id is not None and s_id in sub_profiles_by_sub_id:
            # Сохраняем локальный UUID профиля
            profile["id"] = sub_profiles_by_sub_id[s_id].get("id", str(uuid.uuid4()))
        else:
            profile["id"] = str(uuid.uuid4())

        updated_sub_profiles.append(profile)

    # 4. Объединение профилей и сохранение
    final_profiles = manual_profiles + updated_sub_profiles
    settings.data["profiles"] = final_profiles

    # 5. Кэширование метаданных подписки
    settings.data["subscription_url"] = target_url
    settings.data["subscription_cache"] = data
    sub_status = data.get("status", "active")

    user_info = data.get("user")
    if isinstance(user_info, dict):
        settings.data["subscription_username"] = str(user_info.get("username", ""))
        settings.data["subscription_role"] = str(user_info.get("role", "user"))
        exp_val = str(user_info.get("expires_at", ""))
        settings.data["subscription_expires_at"] = exp_val
        if exp_val:
            try:
                exp_clean = exp_val.replace("Z", "+00:00")
                exp_dt = datetime.fromisoformat(exp_clean)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > exp_dt:
                    sub_status = "expired"
            except Exception:
                pass

    settings.data["subscription_status"] = sub_status

    server_info = data.get("server")
    if isinstance(server_info, dict):
        settings.data["subscription_server_host"] = str(server_info.get("host", ""))
        settings.data["subscription_app_version"] = str(server_info.get("app_version", ""))

    cabinet_url = data.get("cabinet_url") or data.get("dashboard_url")
    if not cabinet_url and isinstance(server_info, dict):
        cabinet_url = server_info.get("cabinet_url") or server_info.get("dashboard_url")
    if not cabinet_url:
        cabinet_url = get_cabinet_url(target_url)
    if cabinet_url:
        settings.data["subscription_cabinet_url"] = str(cabinet_url).strip().rstrip("/")

    settings.data["subscription_last_sync"] = datetime.now().isoformat()
    settings.save()

    msg = f"Подписка успешно обновлена. Получено профилей: {len(updated_sub_profiles)}."
    return (True, msg, updated_sub_profiles)


def get_subscription_info() -> Dict[str, Any]:
    """
    Возвращает сводную информацию о текущей подписке и профилях.
    """
    from utils.config_store import settings

    url = settings.get("subscription_url", "")
    cache = settings.get("subscription_cache", {})
    profiles = [p for p in settings.get_profiles() if p.get("is_subscription") or p.get("sub_id") is not None]

    status = settings.get("subscription_status", "")
    if not status:
        status = "active" if (url or profiles) else "inactive"

    username = settings.get("subscription_username", "")
    if not username and isinstance(cache.get("user"), dict):
        username = str(cache["user"].get("username", ""))
    if not username:
        for p in profiles:
            if p.get("username"):
                username = str(p["username"]).strip()
                break

    server_host = settings.get("subscription_server_host", "")
    if not server_host and isinstance(cache.get("server"), dict):
        server_host = str(cache["server"].get("host", ""))
    if not server_host and url:
        try:
            import urllib.parse
            server_host = urllib.parse.urlparse(url).netloc
        except Exception:
            pass
    if not server_host:
        for p in profiles:
            sh = p.get("server") or p.get("server_host") or (p.get("endpoint", "").split(":")[0] if p.get("endpoint") else "")
            if sh:
                server_host = str(sh).strip()
                break

    expires_at = settings.get("subscription_expires_at", "")
    if not expires_at and isinstance(cache.get("user"), dict):
        expires_at = str(cache["user"].get("expires_at", ""))
    if not expires_at:
        for p in profiles:
            if p.get("expires_at"):
                expires_at = str(p["expires_at"]).strip()
                break

    cabinet_url = settings.get("subscription_cabinet_url", "")
    if not cabinet_url:
        cabinet_url = get_cabinet_url(url)

    days_left: Optional[int] = None
    is_expiring_soon = False
    is_expired = (status == "expired")

    if expires_at:
        try:
            exp_clean = str(expires_at).replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(exp_clean)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            diff = exp_dt - now_dt
            diff_seconds = diff.total_seconds()
            if diff_seconds <= 0:
                is_expired = True
                if status not in ("blocked", "banned"):
                    status = "expired"
                days_left = 0
            else:
                days_left = int(diff.days)
                if 0 <= days_left <= 3:
                    is_expiring_soon = True
        except Exception:
            pass

    return {
        "url": url,
        "cabinet_url": cabinet_url,
        "status": status,
        "username": username,
        "role": settings.get("subscription_role", "user"),
        "expires_at": expires_at,
        "days_left": days_left,
        "is_expiring_soon": is_expiring_soon,
        "is_expired": is_expired,
        "server_host": server_host,
        "app_version": settings.get("subscription_app_version", ""),
        "last_sync": settings.get("subscription_last_sync", ""),
        "profiles_count": len(profiles),
        "profiles": profiles,
        "is_active": bool(url and status == "active" and not is_expired),
        "cache": cache
    }


def clear_subscription() -> bool:
    """
    Удаляет все профили подписки и сбрасывает кэш/URL подписки в настройках.
    Ручные профили пользователя остаются нетронутыми.
    """
    from utils.config_store import settings

    try:
        current_profiles = settings.get_profiles()
        preserved_profiles = [
            p for p in current_profiles
            if not p.get("is_subscription") and p.get("sub_id") is None
        ]
        settings.data["profiles"] = preserved_profiles

        keys_to_clear = [
            "subscription_url",
            "subscription_cache",
            "subscription_cabinet_url",
            "subscription_status",
            "subscription_username",
            "subscription_role",
            "subscription_expires_at",
            "subscription_server_host",
            "subscription_app_version",
            "subscription_last_sync"
        ]
        for k in keys_to_clear:
            settings.data.pop(k, None)

        settings.save()
        return True
    except Exception as e:
        print(f"Error clearing subscription: {e}")
        return False


class SubscriptionManager:
    """
    Фасадный класс для работы с подписками BobrDobr VPN.
    Позволяет вызывать методы как в виде статических функций, так и через экземпляр.
    """
    SubscriptionError = SubscriptionError

    @staticmethod
    def fetch(url: str, timeout: int = 15) -> Dict[str, Any]:
        return fetch_subscription(url, timeout=timeout)

    fetch_subscription = fetch

    @staticmethod
    def sync(url: str = "") -> Tuple[bool, str, List[Dict[str, Any]]]:
        return sync_subscription(url)

    sync_subscription = sync

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return get_subscription_info()

    @staticmethod
    def get_cabinet_url(url: str = "") -> str:
        return get_cabinet_url(url)

    @staticmethod
    def clear() -> bool:
        return clear_subscription()

    @staticmethod
    def format_name(name: str) -> str:
        return format_subscription_profile_name(name)

    @staticmethod
    def convert_connection(conn: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return convert_connection_to_profile(conn)
