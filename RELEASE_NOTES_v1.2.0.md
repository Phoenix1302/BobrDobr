# BobrDobr VPN v1.2.0 Release Notes / Примечания к выпуску

[![Release](https://img.shields.io/badge/release-v1.2.0-blue.svg)](https://github.com/Phoenix1302/BobrDobr/releases/tag/v1.2.0)
[![Go Version](https://img.shields.io/badge/Go-1.24-00ADD8.svg?logo=go)](https://golang.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-0078D6.svg?logo=windows)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)

---

## 🇷🇺 Русский язык

### Обзор релиза BobrDobr VPN v1.2.0

Версия **v1.2.0** представляет собой крупнейшее технологическое обновление BobrDobr VPN. В этом выпуске представлен полностью переработанный нативный Go-движок (`client-go`), бесшовная интеграция с системным компонентом Microsoft WebView2, поддержка высокопроизводительного сетевого драйвера Wintun, кардинальное визуальное обновление интерфейса, а также полное устранение проблем с повышением привилегий Windows и скрытием консольных окон маршрутизации.

---

### 🚀 Новые возможности и архитектура (Features & Architecture)

1. **Полноценный нативный Go-движок (`client-go`) с интеграцией WebView2**
   - Ядро приложения переписано на современном **Go 1.24**, что снизило потребление оперативной памяти, ускорило холодный старт и обеспечило монолитную надежность без громоздких зависимостей.
   - Рендеринг интерфейса построен на базе нативного системного движка **Microsoft WebView2 Evergreen Runtime**, обеспечивающего высокую отзывчивость, плавную анимацию и полную изоляцию контекстов.

2. **Высокопроизводительные драйверы Wintun и протоколы AmneziaWG + OpenConnect (AnyConnect)**
   - Нативная интеграция скоростного сетевого интерфейса **Wintun** обеспечивает максимальную пропускную способность туннеля и минимальные задержки при интенсивной нагрузке.
   - Равнозначная поддержка новейшего защищенного протокола **AmneziaWG** (с маскировкой handshake и защитой от DPI) и корпоративного протокола **OpenConnect / Cisco AnyConnect** с камуфляжем трафика.

3. **Равнозначное визуальное позиционирование протоколов**
   - Устранены искусственные приоритеты в селекторах: оба протокола (AmneziaWG и OpenConnect) обладают равным визуальным весом, интуитивными бейджами и гармоничным цветовым кодированием.

4. **Встроенный валидатор конфигурации подключения в реальном времени**
   - Интеллектуальная система проверки формата конфигураций «на лету» отображает статус `🟢 Конфигурация валидна` либо детально подсвечивает синтаксические и сетевые ошибки до попытки подключения.

5. **Плавная система Toast-уведомлений**
   - Модернизированный менеджер всплывающих уведомлений: новые сообщения плавно сменяют предыдущие без визуального наложения друг на друга и дрожания анимации.

6. **Понятные бейджи маршрутизации**
   - Вместо технического и криптичного обозначения `all` теперь отображается четкий бейдж `Весь трафик`, а при раздельном туннелировании — бейдж `Исключения`.

7. **Полировка визуального оформления карточек**
   - Устранено паразитное неоновое свечение вниз на карточках профилей подключения; подсветка теперь сбалансирована по всему периметру карточки в едином неоновом стиле.

---

### 🐛 Исправления ошибок (Bug Fixes)

- **Win32 Error 740 (`ERROR_ELEVATION_REQUIRED`) в инсталляторе:**
  - В скрипт Inno Setup добавлен флаг `runascurrentuser` для секции `[Run]`. По завершении установки клиент запускается в контексте обычного пользователя без аварийного отказа Windows при деэскалации прав.
- **Сбой запуска скрипта OpenConnect на Windows (`vpnc-script-win.js`):**
  - Устранена ошибка Windows Script Host `Неверная функция (код 1)` при инициализации интерфейса AnyConnect. Скрипт корректно настраивает сетевые шлюзы и DNS-серверы.
- **Полная тишина при применении маршрутов:**
  - Замена вызовов `ws.Exec` на `ws.Run(cmd, 0, true)` с временной буферизацией вывода. Больше никаких мерцающих черных консольных окон cmd.exe во время подключения и отключения VPN.
- **Устранение дубликатов в логах:**
  - Ликвидировано повторное логирование событий проверки обновлений при инициализации и фоновом опросе.
- **Адаптивный футер модального окна управления подпиской:**
  - Исправлена верстка и отступы модального окна — кнопка «Закрыть» больше не обрезается рамкой окна и сохраняет доступность при любых масштабах экрана (DPI).

---

### 🔐 Контрольные суммы и цифровые подписи (Checksums & Authenticode)

Все релизные сборки подписаны сертификатом разработчика со штампом времени DigiCert RFC 3161:
- **Субъект сертификата:** `CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU`
- **Штамп времени:** `DigiCert SHA256 RSA4096 Timestamp Responder` (RFC 3161)

| Файл | Описание | SHA-256 Контрольная сумма |
| :--- | :--- | :--- |
| **`BobrDobr-Setup.exe`** | Официальный инсталлятор (Inno Setup 6) | `01BB68AFAEF1469D4AA214D4812D4F23025E027FC5B74755B996C0A75902EE47` |
| **`BobrDobr.exe`** | Нативный портативный бинарник (Go + WebView2) | `777979048DA8D858E5A1075F8E07187E71CB6D68BEF7DEFEBA367FA54236A64C` |

Проверка контрольной суммы в PowerShell:
```powershell
Get-FileHash BobrDobr-Setup.exe -Algorithm SHA256
Get-AuthenticodeSignature BobrDobr-Setup.exe
```

---
---

## 🇬🇧 English

### BobrDobr VPN v1.2.0 Release Overview

Version **v1.2.0** is the biggest architectural milestone for BobrDobr VPN to date. This release introduces an all-new native Go engine (`client-go`), deep Microsoft WebView2 evergreen runtime integration, high-performance Wintun adapter support, unified protocol UX, real-time configuration validation, smooth notification stacking, and comprehensive fixes for Windows elevation and routing scripts.

---

### 🚀 Features & Architecture

1. **Full Native Go Engine (`client-go`) with WebView2 Integration**
   - The core client was rewritten in modern **Go 1.24**, significantly lowering RAM footprint, accelerating cold boot times, and providing robust single-binary reliability.
   - Native modern UI rendering backed by **Microsoft WebView2 Evergreen Runtime**, ensuring hardware-accelerated animations, responsive components, and tight security isolation.

2. **High-Performance Wintun Driver & Dual Protocol Core (AmneziaWG + OpenConnect)**
   - Native integration with the lightweight, lightning-fast **Wintun** network driver for ultra-low latency and multi-gigabit throughput.
   - Equal support for **AmneziaWG** (advanced obfuscated WireGuard handshake bypassing deep packet inspection) and enterprise-grade **OpenConnect / Cisco AnyConnect** with customizable path cloaking.

3. **Equal Protocol Visual Positioning**
   - Completely neutral visual hierarchy: AmneziaWG and OpenConnect are positioned with identical weight, harmonious color accents, and unambiguous protocol badges.

4. **Real-time Live Configuration Validator**
   - Instant syntax and network endpoint validator showing `🟢 Configuration is valid` in real time or guiding the user with precise inline error messages prior to tunnel creation.

5. **Smooth Non-Stacking Toast Notification System**
   - Redesigned toast dispatcher: subsequent notifications seamlessly replace active toasts without vertical overlap, layout jank, or animation clipping.

6. **Human-Readable Routing Badges**
   - Replaced technical shorthand `all` with a clear `All Traffic` badge, while split-tunneling configurations display an explicit `Exceptions` badge.

7. **Refined Card Visual Styling**
   - Eliminated downward neon shadow bleed on connection cards; lighting effects now wrap uniformly around the card boundaries.

---

### 🐛 Bug Fixes

- **Windows Win32 Error 740 (`ERROR_ELEVATION_REQUIRED`) on Installer Finish:**
  - Added `runascurrentuser` flag to Inno Setup's `[Run]` postinstall action, allowing the client to spawn under the interactive user's standard session token.
- **OpenConnect Windows Routing Failure (`vpnc-script-win.js`):**
  - Resolved `Incorrect function (code 1)` error during AnyConnect adapter initialization; gateways and route metrics are now registered deterministically.
- **Silent Background Route Manipulation:**
  - Transitioned from `ws.Exec` to `ws.Run(cmd, 0, true)` with temporary stream capture. Routing changes operate completely in the background with zero popping black cmd windows.
- **Duplicate Log Entries:**
  - Fixed duplicate "Checking for updates..." log entries produced during startup and periodic background polls.
- **Subscription Modal Layout Clipping:**
  - Fixed footer padding and layout containment so the "Close" button remains fully visible across all DPI scaling levels.

---

### 🔐 Checksums & Digital Signatures

All release assets are cryptographically signed with DigiCert RFC 3161 trusted timestamping:
- **Signer Subject:** `CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU`
- **Timestamp Authority:** `DigiCert SHA256 RSA4096 Timestamp Responder` (RFC 3161)

| Asset | Description | SHA-256 Checksum |
| :--- | :--- | :--- |
| **`BobrDobr-Setup.exe`** | Official Windows Installer (Inno Setup 6) | `01BB68AFAEF1469D4AA214D4812D4F23025E027FC5B74755B996C0A75902EE47` |
| **`BobrDobr.exe`** | Standalone Native Binary (Go + WebView2) | `777979048DA8D858E5A1075F8E07187E71CB6D68BEF7DEFEBA367FA54236A64C` |

Verification via PowerShell:
```powershell
Get-FileHash BobrDobr-Setup.exe -Algorithm SHA256
Get-AuthenticodeSignature BobrDobr-Setup.exe
```
