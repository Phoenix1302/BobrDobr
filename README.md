# БобрДобр VPN (BobrDobr VPN) v1.3.1

[![Release](https://img.shields.io/badge/release-v1.3.1-amber.svg)](https://github.com/Phoenix1302/BobrDobr/releases/tag/v1.3.1)
[![Go Version](https://img.shields.io/badge/Go-1.24-00ADD8.svg?logo=go)](https://golang.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-0078D6.svg?logo=windows)](https://microsoft.com)
[![Installer](https://img.shields.io/badge/Installer-Inno%20Setup%206-blue.svg)](https://jrsoftware.org/isinfo.php)
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)](LICENSE)

Современный высокопроизводительный нативный клиент виртуальных частных сетей (VPN) для Windows 10 и Windows 11 (x64), написанный на чистом **Go 1.24** с киберпанк-интерфейсом на базе **Microsoft Edge WebView2**.

> [!NOTE]
> **Архивный репозиторий / Legacy Archive Notice**  
> Исходный код первой версии клиента на Python 3.11 / PySide6 (Qt) был полностью выведен из основного репозитория и архивирован в отдельном репозитории:  
> 🔗 **[https://github.com/Phoenix1302/bobrdobr-old](https://github.com/Phoenix1302/bobrdobr-old)**

---

## ⚡ Ключевые возможности и архитектура v1.3.1

### 1. Pure Go 1.24 Native Core & Windows Service Management
- **100% Go**: ядро клиента скомпилировано в единый статический бинарник без сторонних интерпретаторов и рантайм-скриптов.
- **Windows Job Objects**: туннельные процессы жестко привязаны к Job Object операционной системы с флагом `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. При любом завершении приложения дочерние процессы гарантированно уничтожаются ядром Windows.
- **DPAPI Безопасность**: учетные данные, пароли и конфигурации профилей шифруются с помощью аппаратного Windows Data Protection API (DPAPI).
- **Стабильная интеграция с системным треем Windows 10 и 11**: контекстное меню надежно удерживает панель скрытых значков (включая XAML-островки Windows 11), корректно закрывается по аппаратному событию `VK_ESCAPE` и не замораживает системную панель задач.

### 2. Киберпанк GUI на базе встроенного Microsoft Edge WebView2
- **Аппаратная неоновая анимация («Бегущая лента»)**: динамический световой луч на GPU (`conic-gradient` + CSS `@property`) с бесшовным переходом цвета из янтарного в изумрудно-зелёный при установлении связи.
- **Бесшовное быстрое переключение серверов (Fast-Switching)**: независимое отслеживание реально подключенного туннеля (`connectedProfileId`). Свободное и плавное переключение между серверами по кнопке «Подключить» без визуальных рассинхронизаций.
- **Встроенные модальные окна и подтверждения**: диалоги с эффектом `backdrop-filter: blur(8px)`, акцентным свечением и поддержкой клавиатуры (`Enter` / `Escape`).
- **Раздел «Авторство и разработка»**: быстрый доступ к официальному репозиторию проекта и профилю автора на GitHub прямо из настроек.

### 3. Pure-Go OpenConnect Worker (CSTP / DTLS)
- **100% Self-Contained**: собственная реализация протокола Cisco AnyConnect / OpenConnect CSTP на чистом Go.
- **Отказ от MinGW DLL**: удалены 18 тяжелых сторонних динамических библиотек (`libgnutls`, `libgmp`, `libxml2`, `zlib` и др.).
- **URL & User-Agent Camouflage**: поддержка маскировки параметров запроса (`?kurwa`) и эмуляции легитимных клиентов.
- **Встроенный Wintun драйвер**: прямое взаимодействие с виртуальным сетевым адаптером Wintun.

### 4. AmneziaWG Tunneling
- **Поддержка обфускации**: совместимость с протоколом AmneziaWG (`amneziawg-go`), включая рандомизацию заголовков (`Jc`, `Jmin`, `Jmax`, `S1`, `S2`, `H1`-`H4`).
- **Защита адаптеров**: автоматическое управление системными маршрутами и DNS-серверами с мгновенной очисткой при дисконнекте.

### 5. Server-First Subscription Management
- **Приоритет сервера**: актуальный статус подписки валидируется на сервере с защитой от флуда и экспоненциальным backoff при `429 Too Many Requests`.
- **Автоматический разрыв туннеля**: при отзыве (`401 Unauthorized`) или истечении подписки (`403 Forbidden`), а также при удалении профиля активный туннель немедленно и корректно разрывается.

### 6. Криптографически подписанный инсталлятор Inno Setup 6
- Полная поддержка установки от имени администратора в `C:\Program Files\BobrDobr VPN`.
- Автоматическая регистрация/дерегистрация автозапуска в реестре Windows.
- Цифровая подпись Authenticode с RFC 3161 Timestamping.

---

## 📁 Структура репозитория

```text
VPN_Windows_Client/
├── .github/workflows/               # GitHub Actions CI/CD (чистый Go 1.24 релизный пайплайн)
├── assets/                          # Иконки приложения (beaver.ico, SVG-ресурсы)
├── bin/windows/                     # Нативные исполняемые модули ядра
│   ├── amneziawg-go.exe             # Сетевой сервис AmneziaWG
│   ├── openconnect-worker.exe       # Pure-Go воркер OpenConnect CSTP/DTLS
│   └── wintun.dll                   # Официальный драйвер Wintun (x64)
├── client-go/                       # Основное приложение на Go
│   ├── build/windows/               # Манифесты, ресурсы (versioninfo.json), ISS скрипт
│   ├── certs/                       # Сертификаты для подписи кода (Authenticode)
│   ├── cmd/bobrdobr/                # Главная точка входа (main.go, syso-ресурсы)
│   ├── pkg/                         # Модули: config, gui, netadapter, tray, vpn, updater
│   ├── scripts/                     # Скрипты сборки и подписи (Build-Installer.ps1)
│   └── vendor/                      # Вендоринг зависимостей Go
├── dist/                            # Готовые собранные дистрибутивы
│   ├── installer/                   # BobrDobr-Setup-v1.3.1.exe, BobrDobr-Setup.exe
│   └── windows/                     # BobrDobr.exe
├── openconnect-worker/              # Исходный код Pure-Go воркера OpenConnect
├── build-go.ps1                     # Локальный скрипт сборки Go-клиента
├── build-openconnect-worker.ps1     # Локальный скрипт сборки OpenConnect воркера
├── RELEASE_NOTES_v1.3.1.md          # Примечания к релизу v1.3.1
└── README.md                        # Документация проекта
```

---

## 🛠️ Сборка из исходников

### Требования:
- Windows 10 / 11 (x64)
- [Go 1.24+](https://golang.org/dl/)
- [Inno Setup 6.2+](https://jrsoftware.org/isdl.php)
- [goversioninfo](https://github.com/josephspurrier/goversioninfo) (`go install github.com/josephspurrier/goversioninfo/cmd/goversioninfo@latest`)
- *(Опционально)* [Podman](https://podman.io/) или Docker для контейнерной компиляции

### Сборка через PowerShell:

```powershell
# 1. Сборка OpenConnect воркера
.\build-openconnect-worker.ps1

# 2. Сборка основного Go клиента и инсталлятора
.\build-go.ps1 -Version "1.3.1"
```

Собранные бинарники и подписанный установщик будут сохранены в каталоге `dist/installer/BobrDobr-Setup-v1.3.1.exe` и `dist/windows/BobrDobr.exe`.

---

## 📄 Лицензия

Проект распространяется под свободной лицензией **GNU General Public License v3.0** (GPLv3). Подробности в файле [LICENSE](LICENSE).
