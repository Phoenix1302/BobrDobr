# БобрДобр VPN | Заповедник гидроинженерии (AmneziaWG & OpenConnect)

Кроссплатформенный (Linux & Windows) настольный GUI-клиент (лаунчер/оркестратор) в фирменном стиле **«БобрДобр»** (`bobrin.netphoenix.ru`) для протоколов:
- **AmneziaWG** (WireGuard с полной защитой от DPI и обфускацией: `Jc`, `Jmin`, `Jmax`, `S1`, `S2`, `H1-H4`)
- **OpenConnect** (AnyConnect, Pulse Connect Secure, GlobalProtect, Juniper, F5 BIG-IP, Fortinet)

---

## 🛡️ Ключевые возможности и архитектура

1. **Строго изолированное окружение сборки через Podman**:
   - Хостовая система полностью чистая — никаких установленных компиляторов, Python, Qt или утилит сборки.
   - Сборка исполняемых файлов производится в контейнерах через монтирование тома:
     ```powershell
     podman run --cgroups=disabled --rm -v "${PWD}:/workspace:Z" vpn-builder-windows
     ```
2. **Полный комплект бинарных файлов ядра в `bin/windows/` и `dist/windows/`**:
   - `amneziawg-go.exe`: скомпилирован из исходного кода под Windows x64.
   - `wintun.dll`: официальный высокопроизводительный драйвер виртуального адаптера Wintun 0.14.1 x64.
   - `openconnect.exe` + полный набор из 15 DLL (GnuTLS, Nettle, GMP, P11-Kit, LibXML2, Zlib и др.).
   - `vpnc-script-win.js`: скрипт настройки маршрутизации и DNS для Windows.
3. **Безопасность учетных данных**:
   - Пароли для OpenConnect передаются через флаг `--passwd-on-stdin` напрямую в изолированный pipe процесса и никогда не светятся в аргументах командной строки (`/proc/*/cmdline` или Диспетчере задач Windows).
4. **Сохранение настроек между запусками**:
   - Запоминание последнего выбранного `.conf` чертежа плотины, значений обфускации, параметров шлюза OpenConnect, размеров окна и активной вкладки.
   - Конфигурационный файл сохраняется в `%APPDATA%\BobrDobr\settings.json` (Windows) / `~/.config/bobrdobr/settings.json` (Linux).
5. **Graceful Shutdown & Защита от зависших сетевых адаптеров**:
   - Дочерние процессы изолированы в отдельных группах процессов (`CREATE_NEW_PROCESS_GROUP` на Windows и `os.setsid` на Linux).
   - При отключении или закрытии окна лаунчер передает `CTRL_BREAK_EVENT` / `SIGINT`, корректно освобождает адаптеры Wintun и сбрасывает сетевые маршруты.
6. **Фирменный дизайн «БобрДобр»**:
   - Палитра речного заповедника: `#0f1416`, `#182226`, `#24343b`, янтарь `#d97706`.
   - Векторная эмблема бобра (SVG), чистая верстка без ломающихся эмодзи (tofu box `▯`), удобная двухрядная сетка параметров маскировки.
   - Потоковый перехват логов в реальном времени с гидротехническими каналами (`[БОБР]`, `[ПОТОК]`, `[ВОДОВОРОТ]`, `[ПРОТЕЧКА]`).

---

## 📁 Структура проекта

```text
VPN_Windows_Client/
├── bin/                             # Исполняемые файлы ядра и библиотеки
│   ├── linux/                       # amneziawg-go, openconnect, vpnc-script
│   └── windows/                     # amneziawg-go.exe, openconnect.exe, wintun.dll, DLLs
├── dist/                            # Готовые собранные дистрибутивы
│   ├── linux/                       # BobrDobr-VPN (автономный бинарник Linux)
│   └── windows/                     # BobrDobr-VPN.exe + wintun.dll + amneziawg-go + openconnect
├── docker/                          # Контейнеры и сборочные скрипты
│   ├── Containerfile.windows        # Headless сборка под Windows через Wine в Podman
│   └── scripts/
│       ├── build_linux.sh           # Скрипт сборки под Linux внутри контейнера
│       └── build_windows.sh         # Скрипт сборки под Windows внутри контейнера
├── src/                             # Исходный код приложения
│   ├── assets/
│   │   └── beaver.svg               # Векторный логотип бобра
│   ├── core/                        # Менеджеры процессов
│   │   ├── amnezia.py               # Оркестратор AmneziaWG (обфускация Jc, Jmin, Jmax, S1, S2, H1-H4)
│   │   ├── openconnect.py           # Оркестратор OpenConnect (--passwd-on-stdin)
│   │   └── vpn_manager.py           # Базовый класс жизненного цикла процессов
│   ├── gui/                         # Графический интерфейс на PySide6
│   │   ├── log_viewer.py            # Выдвижная панель гидротехнических логов
│   │   ├── styles.py                # Палитра БобрДобр QSS
│   │   ├── tab_amnezia.py           # Вкладка плотины AmneziaWG
│   │   └── tab_openconnect.py       # Вкладка шлюза OpenConnect
│   ├── utils/
│   │   ├── config_store.py          # Постоянное хранилище настроек (settings.json)
│   │   └── platform_helper.py       # Детекция OS, поиск бинарников, права админа
│   └── main.py                      # Точка входа GUI
├── Containerfile.build              # Podman-контейнер сборки под Linux
├── Makefile                         # Автоматизация сборки в Podman
├── build.sh                         # Скрипт сборки для Linux
├── build.ps1                        # Скрипт сборки для Windows (PowerShell)
└── README.md                        # Документация проекта
```

---

## 🚀 Запуск и сборка

### Запуск готового приложения на Windows:
Перейдите в директорию `dist\windows` и запустите:
```powershell
.\dist\windows\BobrDobr-VPN.exe
```
*(Для создания сетевых Wintun-интерфейсов запуск рекомендуется производить с правами Администратора)*.

### Сборка под Windows через Podman (1 команда):
```powershell
podman build -t vpn-builder-windows -f docker/Containerfile.windows .
podman run --cgroups=disabled --rm -v "${PWD}:/workspace:Z" vpn-builder-windows
```

### Сборка под Linux через Podman:
```bash
podman build -t vpn-builder-linux -f Containerfile.build .
podman run --cgroups=disabled --rm -v "${PWD}:/workspace:Z" vpn-builder-linux
```

