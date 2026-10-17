# Windows Native Binaries and Drivers

Поместите сюда исполняемые файлы и системные драйверы для Windows x64:

- `amneziawg-go.exe` — Go-реализация Amnezia WireGuard с поддержкой обфускации.
- `wintun.dll` — официальная библиотека Wintun (версия 0.14.1+), необходимая для создания TAP/TUN интерфейсов в Windows.
- `openconnect.exe` — CLI-клиент OpenConnect под Windows.
- `vpnc-script-win.js` — скрипт конфигурации маршрутизации и DNS для OpenConnect под Windows.
- Сопутствующие DLL (если `openconnect.exe` скомпилирован динамически: `libxml2.dll`, `libgnutls.dll`, `libgmp.dll` и др.).

При сборке через Podman (`Containerfile.windows`) содержимое этой папки автоматически включается в `dist/windows/bin/`.
Если бинарники отсутствуют в локальной папке `bin/windows/`, лаунчер попытается обнаружить их в системном `%PATH%`.
