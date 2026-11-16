# BobrDobr VPN v1.3.2 Release Notes / Примечания к выпуску

[![Release](https://img.shields.io/badge/release-v1.3.2-amber.svg)](https://github.com/Phoenix1302/BobrDobr/releases/tag/v1.3.2)
[![Go Version](https://img.shields.io/badge/Go-1.24-00ADD8.svg?logo=go)](https://golang.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-0078D6.svg?logo=windows)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)

---

## 🇷🇺 Русский язык

### Обзор релиза BobrDobr VPN v1.3.2

В версии **v1.3.2** оптимизировано сетевое взаимодействие и повышена стабильность защищённого соединения OpenConnect, модернизирован TLS-стек клиента с поддержкой современных стандартов браузерного уровня, а также обеспечена надёжная совместимость прикладного уровня AnyConnect CSTP.

---

### 🚀 Ключевые изменения (Major Highlights)

1. **Модернизация TLS-стека сетевого ядра (Browser-Grade TLS Transport)**:
   - В нативный Go-компонент `openconnect-worker` интегрирован усовершенствованный транспорт на базе библиотеки `uTLS`.
   - Реализована полноценная поддержка современных веб-стандартов параметров TLS-рукопожатия (включая спецификацию современных десктопных браузеров, расширения GREASE, оптимальный порядок шифронаборов, кривые X25519, Supported Versions и Key Share).
   - Существенно повышена стабильность и надёжность установления соединений в нестабильных сетевых условиях.

2. **Оптимизация прикладного уровня AnyConnect CSTP**:
   - Усовершенствована логика согласования параметров сессии защищённого туннеля между клиентом и сервером.
   - Обеспечена безупречная совместимость со шлюзами AnyConnect и серверами `ocserv` при сохранении целостности сетевых заголовков.

3. **Синхронизация сетевых модулей и модульное тестирование**:
   - Обновлены модули аутентификации (`auth`), сессий (`session`) и туннеля (`vpn/tunnel`, `vpn/tls`) в `openconnect-worker`.
   - Добавлен комплекс модульных тестов для валидации корректности и надёжности защищённого соединения.

---

### 🔐 Контрольные суммы и цифровые подписи (Checksums & Signatures)

Все исполняемые файлы подписаны официальным сертификатом с доверенным штампом времени DigiCert RFC 3161:
- **Инсталлятор:** `BobrDobr-Setup-v1.3.2.exe`
- **Размер:** 10.0 MB (10 523 272 байт)
- **SHA-256 (Setup):** `F957E78627160C858BF894F07FD1783689A6408AAF7195442A9953E770F150A0`
- **SHA-256 (BobrDobr.exe):** `50F31F87900EC7BBE77CC2455932E40F5448C85E8358A487EDC47EEF7DA137EC`
- **Субъект сертификата:** `CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU`
- **Центр штампа времени:** `DigiCert SHA256 RSA4096 Timestamp Responder 2026 1` (RFC 3161)
- **Статус подписи:** `Valid`
