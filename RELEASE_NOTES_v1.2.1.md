# BobrDobr VPN v1.2.1 Release Notes / Примечания к выпуску

[![Release](https://img.shields.io/badge/release-v1.2.1-blue.svg)](https://github.com/Phoenix1302/BobrDobr/releases/tag/v1.2.1)
[![Go Version](https://img.shields.io/badge/Go-1.24-00ADD8.svg?logo=go)](https://golang.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-0078D6.svg?logo=windows)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)

---

## 🇷🇺 Русский язык

### Обзор релиза BobrDobr VPN v1.2.1

Версия **v1.2.1** — это обновление стабильности и пользовательского опыта BobrDobr VPN. В этом выпуске реализовано корректное завершение сессий OpenConnect (AnyConnect) с отправкой BYE-пакета серверу, добавлена нативная интеграция с буфером обмена Windows без системных диалогов, внедрено сохранение параметров подписки и счетчик оставшихся дней, устранены проблемы с переносом строк в интерфейсе, а инсталлятор получил версионированное имя файла и надежный запуск без ошибок повышения привилегий.

---

### 🚀 Новые возможности и улучшения (Features & Improvements)

1. **Штатное завершение сессий OpenConnect (Graceful BYE Handshake)**
   - Дочерний процесс OpenConnect теперь запускается с флагами `CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP` в фоновом режиме (`SW_HIDE`).
   - При отключении клиентом вызывается Win32 API `AttachConsole`, после чего направляется корректный сигнал `CTRL_C_EVENT`.
   - OpenConnect успевает выполнить `openconnect_bye()` и отправляет серверу CSTP AnyConnect BYE-пакет. В результате сервер закрывает сессию чисто с кодом `reason: user request` вместо аварийного `unspecified error`, освобождая ресурсы на шлюзе.

2. **Нативная интеграция с системным буфером обмена Windows**
   - Интегрировано прямое чтение буфера обмена через Win32 API (`OpenClipboard`, `GetClipboardData` `CF_UNICODETEXT=13`).
   - Вставка ссылок на подписки теперь работает мгновенно в один клик без системных предупреждений безопасности и всплывающих окон подтверждения.

3. **Кэширование данных подписки и таймер окончания с правильным склонением**
   - Метаданные подписки сохраняются на диск: при перезапуске приложения параметры восстанавливаются мгновенно без раздражающего статуса «Бессрочно», после чего выполняется бесшумная фоновая синхронизация с сервером.
   - Добавлен наглядный обратный отсчет оставшихся дней с соблюдением грамматических правил русского языка (например, `(остался 1 день)`, `(осталось 2 дня)`, `(осталось 25 дней)`).

4. **Адаптивная верстка модального окна подписки**
   - Увеличена максимальная ширина окна и переработана сетка параметров (`minmax(320px, 1.25fr) minmax(210px, 1fr)`) с применением `white-space: nowrap`.
   - Полностью исключен некрасивый перенос даты окончания подписки на несколько строк.

5. **Полировка интерфейса карточек и модальных окон**
   - На карточке подключения кнопка настроек возвращена к классической аккуратной шестеренке `⚙ Настройки`.
   - В диалоге добавления подключения иконка молнии заменена на вилку питания `🔌`.
   - Бейджи маршрутизации стандартизированы до `ALL` и `BYPASS` с удобными подсказками на русском языке при наведении мыши.

6. **Улучшения инсталлятора**
   - Дистрибутив теперь собирается с суффиксом версии в имени файла (`BobrDobr-Setup-v1.2.1.exe`), сохраняя при этом универсальную копию `BobrDobr-Setup.exe`.
   - Оптимизирована директива `shellexec` в сценарии Inno Setup для чистого запуска после завершения установки без ошибки Win32 740 (`ERROR_ELEVATION_REQUIRED`).

---

### 🔐 Контрольные суммы и цифровые подписи (Checksums & Signatures)

Все исполняемые файлы подписаны официальным сертификатом разработчика с доверенным штампом времени DigiCert RFC 3161:
- **Субъект сертификата:** `CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU`
- **Центр штампа времени:** `DigiCert SHA256 RSA4096 Timestamp Responder 2026 1` (RFC 3161)

| Файл | Описание | SHA-256 Контрольная сумма |
| :--- | :--- | :--- |
| **`BobrDobr-Setup-v1.2.1.exe`** | Официальный инсталлятор (с указанием версии) | `430DC38DB2540563E1ECAD2ACBE92606679EBF3373BAA0EA552DF51E64968885` |
| **`BobrDobr-Setup.exe`** | Официальный инсталлятор (универсальный) | `430DC38DB2540563E1ECAD2ACBE92606679EBF3373BAA0EA552DF51E64968885` |
| **`BobrDobr.exe`** | Нативный портативный бинарник (Go + WebView2) | `C915747C499D15BA4BBF1E9C0FFB4BE5AF2CDA203047521489A45DDB5879FE12` |

Проверка контрольной суммы в PowerShell:
```powershell
Get-FileHash BobrDobr-Setup-v1.2.1.exe -Algorithm SHA256
Get-AuthenticodeSignature BobrDobr-Setup-v1.2.1.exe
```

---
---

## 🇬🇧 English

### BobrDobr VPN v1.2.1 Release Overview

Version **v1.2.1** brings critical reliability and user experience enhancements to BobrDobr VPN. This release delivers graceful CSTP AnyConnect session termination with BYE packet delivery, native Win32 clipboard integration for permissionless subscription pasting, local subscription persistence with Russian pluralization day countdowns, improved modal typography, and updated installer packaging.

---

### 🚀 Features & Improvements

1. **OpenConnect Graceful Session Termination (BYE Handshake)**
   - Child process spawning now configures `CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP` alongside `SW_HIDE`.
   - On disconnect, the client attaches to the dedicated console via Win32 `AttachConsole` and delivers a clean `CTRL_C_EVENT`.
   - OpenConnect successfully executes `openconnect_bye()`, transmitting the AnyConnect CSTP BYE packet. Server sessions close gracefully with `reason: user request` instead of abrupt `unspecified error`, cleaning up server state immediately.

2. **Native Windows Clipboard Integration**
   - Implemented native Win32 clipboard APIs (`OpenClipboard`, `GetClipboardData` `CF_UNICODETEXT=13`).
   - Pasting subscription links works instantly with a single click, completely bypassing browser permission prompts and confirmation dialogs.

3. **Subscription Persistence & Expiry Countdown**
   - Cached subscription metadata locally: connection parameters load instantly upon application launch without temporary "Perpetual" flash, followed by a transparent background refresh.
   - Added an intuitive countdown showing days remaining with proper pluralization rules.

4. **Subscription Modal Layout & Text Wrapping Fix**
   - Expanded modal width and reworked the grid layout (`minmax(320px, 1.25fr) minmax(210px, 1fr)`) with `white-space: nowrap`.
   - Expiration dates and metadata now render on a single clean line without awkward wrapping.

5. **Connection Card & Modal UX Polish**
   - Unified connection card settings trigger to a standard gear icon `⚙ Settings`.
   - Replaced lightning bolt with a power plug icon `🔌` in the connection creation modal.
   - Standardized routing badges to `ALL` / `BYPASS` with localized tooltips on hover.

6. **Installer Packaging & Elevation Polish**
   - The installer is now distributed with an explicit version suffix (`BobrDobr-Setup-v1.2.1.exe`) alongside `BobrDobr-Setup.exe`.
   - Confirmed `shellexec` elevation handling in Inno Setup to eliminate Win32 error 740 on completion.

---

### 🔐 Checksums & Digital Signatures

All release assets are cryptographically signed with DigiCert RFC 3161 trusted timestamping:
- **Signer Subject:** `CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU`
- **Timestamp Authority:** `DigiCert SHA256 RSA4096 Timestamp Responder 2026 1` (RFC 3161)

| Asset | Description | SHA-256 Checksum |
| :--- | :--- | :--- |
| **`BobrDobr-Setup-v1.2.1.exe`** | Official Windows Installer (versioned) | `430DC38DB2540563E1ECAD2ACBE92606679EBF3373BAA0EA552DF51E64968885` |
| **`BobrDobr-Setup.exe`** | Official Windows Installer (universal) | `430DC38DB2540563E1ECAD2ACBE92606679EBF3373BAA0EA552DF51E64968885` |
| **`BobrDobr.exe`** | Standalone Native Binary (Go + WebView2) | `C915747C499D15BA4BBF1E9C0FFB4BE5AF2CDA203047521489A45DDB5879FE12` |

Verification via PowerShell:
```powershell
Get-FileHash BobrDobr-Setup-v1.2.1.exe -Algorithm SHA256
Get-AuthenticodeSignature BobrDobr-Setup-v1.2.1.exe
```

**Full Changelog**: https://github.com/Phoenix1302/BobrDobr/compare/v1.2.0...v1.2.1
