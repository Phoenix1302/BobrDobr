# BobrDobr VPN v1.2.2 Release Notes / Примечания к выпуску

[![Release](https://img.shields.io/badge/release-v1.2.2-blue.svg)](https://github.com/Phoenix1302/BobrDobr/releases/tag/v1.2.2)
[![Go Version](https://img.shields.io/badge/Go-1.24-00ADD8.svg?logo=go)](https://golang.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-0078D6.svg?logo=windows)](https://microsoft.com)
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)

---

## 🇷🇺 Русский язык

### Обзор релиза BobrDobr VPN v1.2.2

Версия **v1.2.2** представляет крупное функциональное обновление системы обслуживания клиента BobrDobr VPN. В этом выпуске реализована полноценная интерактивная система обновления приложения внутри интерфейса (In-App Updater), создана новая надежная подсистема логирования с выделенной подпапкой `log/` и автоматической ротацией, исправлена блокировка вывода в GUI-подсистеме Windows, а также проведена полировка UI-компонентов.

---

### 🚀 Новые возможности и улучшения (Features & Improvements)

1. **Интерактивная система обновления (Interactive In-App Updater)**
   - **Уведомление о новой версии:** Всплывающий тост (Toast) теперь снабжен интерактивной кнопкой `[ Подробнее ]`, открывающей полноценное диалоговое окно обновления.
   - **Модальное окно обновления (`#update-modal`):** Отображает текущую и доступную версии, подробный список изменений (changelog), статус проверки и анимированный прогресс-бар загрузки с индикацией процентов.
   - **Гибкое управление обновлением:**
     - ⏰ **«Отложить»:** Откладывает напоминание об обновлении до следующего перезапуска приложения (snooze для текущей сессии).
     - 🌐 **«Страница релиза»:** Мгновенный переход к странице релиза на GitHub в системном браузере по умолчанию.
     - ⬇️ **«Установить обновление»:** Автоматический запуск процесса скачивания и установки в один клик.
   - **Фоновая загрузка и изоляция:** Инсталлятор загружается в выделенную директорию `%LOCALAPPDATA%\BobrDobr\updates\`.
   - **Автоматическая очистка старых дистрибутивов:** Метод `updater.CleanupOldInstallers()` при старте приложения безопасно удаляет временные файлы инсталляторов предыдущих версий.
   - **Безопасное завершение (Safe Shutdown Handshake):** Перед запуском инсталлятора клиент штатно останавливает активное VPN-соединение, скрывает иконку из трея и освобождает глобальный мьютекс Windows, гарантируя отсутствие конфликтов блокировки файлов.

2. **Новая система логирования в подпапке `log/` и автоматическая ротация**
   - **Выделенный каталог:** Файлы логов перенесены из корневого каталога профиля в специализированную подпапку `%APPDATA%\BobrDobr\log\bobrdobr.log`.
   - **Исправление блокировки Win32 Subsystem:** Устранена ошибка, при которой запуск в оконной подсистеме Windows (`-H=windowsgui`) с невалидным файловым дескриптором `os.Stdout` препятствовал записи логов на диск.
   - **Автоматическая ротация по размеру:** При достижении размера 5 МБ текущий лог-файл архивируется с таймстемпом `bobrdobr-YYYY-MM-DD-HHMMSS.log`, а запись продолжается в чистый файл.
   - **Политика хранения и очистки архивов:** Реализовано автоматическое удаление архивов старше 14 дней с сохранением не более 7 последних архивных файлов.
   - **Миграция и очистка legacy-логов:** Устаревшие файлы логов прошлых версий в корневом каталоге конфигурации автоматически выявляются и удаляются при запуске.

3. **Полировка интерфейса и компонентов (UI Polish)**
   - Обновлен дизайн и сглаживание бейджей маршрутизации (`ALL` / `BYPASS`).
   - Улучшена типографика и контрастность кнопок управления в модальных окнах.
   - Устранены микрозадержки при вызове диалоговых окон.

---

### 🔐 Контрольные суммы и цифровые подписи (Checksums & Signatures)

Все исполняемые файлы подписаны официальным сертификатом разработчика с доверенным штампом времени DigiCert RFC 3161:
- **Субъект сертификата:** `CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU`
- **Центр штампа времени:** `DigiCert SHA256 RSA4096 Timestamp Responder 2026 1` (RFC 3161)

| Файл | Описание | Размер | SHA-256 Контрольная сумма |
| :--- | :--- | :--- | :--- |
| **`BobrDobr-Setup-v1.2.2.exe`** | Официальный инсталлятор (с указанием версии) | 10 152 592 байт (9.68 МБ) | `4230657F14083A7FA02E61118D8ADA2ED0849EE30DA279ECE402149FA3248580` |
| **`BobrDobr-Setup.exe`** | Официальный инсталлятор (универсальный) | 10 152 592 байт (9.68 МБ) | `4230657F14083A7FA02E61118D8ADA2ED0849EE30DA279ECE402149FA3248580` |
| **`BobrDobr.exe`** | Нативный портативный бинарник (Go + WebView2) | 7 695 808 байт (7.34 МБ) | `341ACA1E366DCD3EEA92E79561501ECA5D0939954582D0BE60F5DE68E2815EF9` |

Проверка контрольной суммы в PowerShell:
```powershell
Get-FileHash BobrDobr-Setup-v1.2.2.exe -Algorithm SHA256
Get-AuthenticodeSignature BobrDobr-Setup-v1.2.2.exe
```

---
---

## 🇬🇧 English

### BobrDobr VPN v1.2.2 Release Overview

Version **v1.2.2** is a major maintenance and lifecycle update for BobrDobr VPN. This release introduces a fully-featured interactive in-app updater with download progress tracking, a dedicated high-performance logging subsystem located in `log/` with size-based rotation and retention cleanup, fixes a Win32 GUI subsystem stdout descriptor issue, and brings visual polish across interface components.

---

### 🚀 Features & Improvements

1. **Interactive In-App Updater**
   - **Update Notification Toast:** Update banners now feature an interactive `[ Details / Подробнее ]` action button leading directly to the update modal.
   - **Modern Update Modal (`#update-modal`):** Displays current vs. target versions, detailed markdown-formatted changelog, live status indicator, and percentage download progress bar.
   - **Action Controls:**
     - ⏰ **"Snooze":** Postpones update reminders for the remainder of the current application session.
     - 🌐 **"Release Page":** Opens the official GitHub release page in the default web browser.
     - ⬇️ **"Install Update":** Initiates one-click background download and installation.
   - **Isolated Staging Directory:** Installers are downloaded to `%LOCALAPPDATA%\BobrDobr\updates\`.
   - **Automatic Cleanup:** `updater.CleanupOldInstallers()` safely clears outdated setup binaries upon application startup.
   - **Safe Shutdown Handshake:** Prior to launching the installer, the client shuts down the active VPN tunnel, withdraws the tray icon, and releases the single-instance Win32 mutex to prevent file lock contention.

2. **Dedicated Logging Subsystem in `log/` & Automatic Rotation**
   - **Dedicated Directory Structure:** Application logs are moved from root config into `%APPDATA%\BobrDobr\log\bobrdobr.log`.
   - **Win32 Subsystem Stdout Fix:** Resolved an issue under `-H=windowsgui` where invalid `os.Stdout` descriptors blocked log writing to disk.
   - **Size-Based Log Rotation:** Automatically rolls over active logs at 5 MB into timestamped archives (`bobrdobr-YYYY-MM-DD-HHMMSS.log`).
   - **Log Retention Policy:** Enforces a maximum archive retention of 14 days and a hard cap of 7 archives.
   - **Legacy Log Pruning:** Obsolete log files from previous versions in the root configuration directory are cleaned up during initial startup.

3. **User Interface Polish**
   - Refined routing badges (`ALL` / `BYPASS`) styling and contrast.
   - Enhanced modal action button states and responsiveness.
   - Streamlined transition animations and modal backdrop behaviors.

---

### 🔐 Checksums & Digital Signatures

All release assets are cryptographically signed with DigiCert RFC 3161 trusted timestamping:
- **Signer Subject:** `CN=BobrDobr Hydro-engineering Team, O=BobrDobr Hydro-engineering Team, C=RU`
- **Timestamp Authority:** `DigiCert SHA256 RSA4096 Timestamp Responder 2026 1` (RFC 3161)

| Asset | Description | Size | SHA-256 Checksum |
| :--- | :--- | :--- | :--- |
| **`BobrDobr-Setup-v1.2.2.exe`** | Official Windows Installer (versioned) | 10,152,592 bytes (9.68 MB) | `4230657F14083A7FA02E61118D8ADA2ED0849EE30DA279ECE402149FA3248580` |
| **`BobrDobr-Setup.exe`** | Official Windows Installer (universal) | 10,152,592 bytes (9.68 MB) | `4230657F14083A7FA02E61118D8ADA2ED0849EE30DA279ECE402149FA3248580` |
| **`BobrDobr.exe`** | Standalone Native Binary (Go + WebView2) | 7,695,808 bytes (7.34 MB) | `341ACA1E366DCD3EEA92E79561501ECA5D0939954582D0BE60F5DE68E2815EF9` |

Verification via PowerShell:
```powershell
Get-FileHash BobrDobr-Setup-v1.2.2.exe -Algorithm SHA256
Get-AuthenticodeSignature BobrDobr-Setup-v1.2.2.exe
```

**Full Changelog**: https://github.com/Phoenix1302/BobrDobr/compare/v1.2.1...v1.2.2
