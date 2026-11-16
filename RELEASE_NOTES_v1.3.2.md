# BobrDobr VPN v1.3.2 Release Notes / Примечания к выпуску

[![Release](https://img.shields.io/badge/release-v1.3.2-amber.svg)](https://github.com/Phoenix1302/BobrDobr/releases/tag/v1.3.2)
[![Go Version](https://img.shields.io/badge/Go-1.24-00ADD8.svg?logo=go)](https://golang.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-0078D6.svg?logo=windows)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)

---

## 🇷🇺 Русский язык

### Обзор релиза BobrDobr VPN v1.3.2

В версии **v1.3.2** реализована полная маскировка TLS-рукопожатия протокола OpenConnect под браузер Google Chrome (uTLS Chrome Fingerprint & Anti-DPI), обеспечена строгая совместимость прикладного уровня AnyConnect CSTP с принудительным ALPN `http/1.1`, а также синхронизированы все компоненты сборки, инсталлятора и манифестов.

---

### 🚀 Ключевые изменения (Major Highlights)

1. **Эмуляция TLS-отпечатка Google Chrome (uTLS Chrome Fingerprint & Anti-DPI)**:
   - В нативный Go-компонент `openconnect-worker` интегрирована библиотека `github.com/refraction-networking/utls`.
   - Инициализация TLS-сессии теперь использует спецификацию `HelloChrome_Auto`, полностью повторяющую отпечаток десктопного Google Chrome на Windows (JA3/JA4, расширения GREASE, точный порядок шифронаборов, кривые X25519, Supported Versions и Key Share).
   - Для глубоких систем анализа трафика (DPI/ТСПУ) исходящее рукопожатие OpenConnect выглядит как стандартная веб-сессия легитимного браузера, исключая выявление по специфическим сигнатурам стандартных OpenSSL-клиентов.

2. **Строгая совместимость с протоколом AnyConnect CSTP (Enforced ALPN `http/1.1`)**:
   - Реализована точечная модификация ALPN-расширения (`ALPNExtension`) в структуре Client Hello: протокол принудительно согласовывает только `http/1.1`.
   - Это гарантирует 100% совместимость со спецификацией AnyConnect/CSTP и серверами `ocserv`, сохраняя при этом все остальные параметры и заголовки браузерного Client Hello неизменными.

3. **Синхронизация сетевых модулей и модульное тестирование**:
   - Обновлены модули аутентификации (`auth`), сессий (`session`) и туннеля (`vpn/tunnel`, `vpn/tls`) в `openconnect-worker` для сквозной работы через защищённый `uTLS` интерфейс.
   - Добавлен комплекс модульных тестов (`openconnect-worker/auth/utls_test.go`), валидирующий генерацию отпечатков и корректность ALPN при установлении сессии.

4. **Обновление окружения сборки и компонентов**:
   - Версия приложения централизованно повышена до **1.3.2** во всех подсистемах: Go-бэкенде (`main.go`), пользовательском интерфейсе WebView2 (`index.html`), службе автообновления (`updater.go`), инсталляторе Inno Setup (`BobrDobr-Setup.iss`) и системном манифесте ресурсов Windows (`versioninfo.json`).
   - Исполняемые файлы `BobrDobr.exe`, `openconnect-worker.exe` и инсталлятор пересобраны и подписаны цифровым сертификатом с доверенным штампом времени DigiCert RFC 3161.

---

### 🔐 Контрольные суммы и цифровые подписи (Checksums & Signatures)

Все исполняемые файлы подписаны официальным сертификатом с доверенным штампом времени DigiCert RFC 3161:
- **Инсталлятор:** `BobrDobr-Setup-v1.3.2.exe`
- **Размер:** 10.0 MB (10 523 272 байт)
- **SHA-256 (Setup):** `F957E78627160C858BF894F07FD1783689A6408AAF7195442A9953E770F150A0`
- **SHA-256 (BobrDobr.exe):** `50F31F87900EC7BBE77CC2455932E40F5448C85E8358A487EDC47EEF7DA137EC`
- **SHA-256 (openconnect-worker.exe):** `648F3B3D05317109ECBF5FBB3D8ED59F6988BBB18A1939004E2AB648F7FF6D33`
- **Субъект сертификата:** `CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU`
- **Центр штампа времени:** `DigiCert SHA256 RSA4096 Timestamp Responder 2026 1` (RFC 3161)
- **Статус подписи:** `Valid`
