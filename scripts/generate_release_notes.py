#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
BobrDobr VPN — Release Notes Generator
==============================================================================
Специализированный генератор описаний релизов для GitHub Releases и gh release.
Парсит CHANGELOG.md проекта, извлекает заметки для указанной версии
(или последнего релиза) и оформляет их в аутентичной гидроинженерной эстетике
БобрДобр с GitHub-алертами (> [!NOTE], > [!TIP]), эмодзи и инструкциями.

Использование:
    python scripts/generate_release_notes.py --version 1.1.1
    python scripts/generate_release_notes.py --version latest -o release_v1.1.1.md
    python scripts/generate_release_notes.py --list-versions
    python scripts/generate_release_notes.py --version 1.1.1 --title-only
==============================================================================
"""

import argparse
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# Каталог тем и слоганов гидроинженерии для известных релизов
RELEASE_TAGLINES: Dict[str, str] = {
    "1.1.1": "Инженерный апгрейд плотины & Быстрый сетевой шлюз",
    "1.1.0": "Центр управления подписками, морозный статус и камуфляж OpenConnect",
    "1.0.13": "Криптографическая защита конфигураций и ротация бэкапов",
    "1.0.12": "Мгновенный холодный запуск на HDD и гибридный лончер",
    "1.0.11": "Нулевая задержка AmneziaWG (0 мс) и нативный Win32 API стек",
    "1.0.10": "Версионированные сборки и автоматический перезапуск",
    "1.0.9": "Изоляция настроек Portable/Installed и сертификаты SSL",
    "1.0.8": "Модуль фонового обновления GitHub Releases",
}

DEFAULT_TAGLINE = "Плановое укрепление шлюзов и турбин плотины"


class ChangelogEntry:
    """Представление одной версии в CHANGELOG.md."""

    def __init__(self, version: str, date: Optional[str], raw_content: str):
        self.version = version.lstrip("v")
        self.date = date or datetime.now().strftime("%Y-%m-%d")
        self.raw_content = raw_content.strip()

    def __repr__(self) -> str:
        return f"<ChangelogEntry v{self.version} ({self.date})>"


class ChangelogParser:
    """Парсер для извлечения записей из CHANGELOG.md."""

    HEADER_PATTERN = re.compile(
        r"^##\s+\[?v?([0-9]+\.[0-9]+\.[0-9]+(?:-[\w.]+)?)\]?\s*(?:-\s*(\d{4}-\d{2}-\d{2}))?",
        re.MULTILINE,
    )

    def __init__(self, changelog_path: str):
        self.changelog_path = os.path.abspath(changelog_path)
        if not os.path.isfile(self.changelog_path):
            raise FileNotFoundError(f"Файл истории изменений не найден: {self.changelog_path}")
        self._entries: List[ChangelogEntry] = []
        self._parse()

    def _parse(self) -> None:
        with open(self.changelog_path, "r", encoding="utf-8") as f:
            text = f.read()

        matches = list(self.HEADER_PATTERN.finditer(text))
        if not matches:
            return

        for i, match in enumerate(matches):
            version = match.group(1).strip()
            date = match.group(2).strip() if match.group(2) else None
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunk = text[start_pos:end_pos].strip()

            # Удаляем разделители "---" в конце блока
            chunk = re.sub(r"\n+---\s*$", "", chunk).strip()
            self._entries.append(ChangelogEntry(version=version, date=date, raw_content=chunk))

    def list_versions(self) -> List[str]:
        return [e.version for e in self._entries]

    def get_entry(self, version: str) -> Optional[ChangelogEntry]:
        ver_norm = version.lstrip("v").strip().lower()
        if ver_norm in ("latest", "current", ""):
            return self._entries[0] if self._entries else None

        for entry in self._entries:
            if entry.version.lower() == ver_norm:
                return entry
        return None


class BobrReleaseNotesBuilder:
    """Генератор красивых GitHub Release Notes в стиле BobrDobr VPN."""

    def __init__(self, entry: ChangelogEntry):
        self.entry = entry
        self.version = entry.version
        self.date = entry.date
        self.tagline = RELEASE_TAGLINES.get(self.version, DEFAULT_TAGLINE)

    def get_title(self) -> str:
        """Возвращает строку заголовка релиза для gh release / GitHub UI."""
        return f"🦫 БобрДобр VPN v{self.version} — {self.tagline}"

    def build_markdown(self, include_title: bool = True) -> str:
        """Собирает полный документ Markdown для страницы релизов GitHub."""
        parts: List[str] = []

        if include_title:
            parts.append(f"# {self.get_title()}\n")

        # Плашка метаданных
        parts.append(
            f"> 📅 **Дата спуска на воду**: {self.date} | "
            f"🏷️ **Версия плотины**: `v{self.version}` | "
            f"🌊 **Статус шлюзов**: Высокая готовность (Production Stable)\n"
        )

        # Гидроинженерное приветствие
        parts.append(self._generate_greeting())

        # GitHub-алерты (Clean Alerts)
        parts.append(self._generate_alerts())

        # Ключевые нововведения (Feature Highlights)
        highlights = self._generate_highlights()
        if highlights:
            parts.append(highlights)

        # Полный журнал изменений из CHANGELOG
        parts.append(self._generate_detailed_changelog())

        # Инструкция по установке и обновлению
        parts.append(self._generate_install_guide())

        # Бобровый эпилог и подпись
        parts.append(self._generate_footer())

        return "\n".join(parts)

    def _generate_greeting(self) -> str:
        return (
            "Приветствуем строителей и хранителей свободных цифровых заводей! 🌲🦫\n\n"
            f"Бригада гидроинженеров **БобрДобр** завершила масштабную модернизацию гидроузла "
            f"версии **v{self.version}**. Мы укрепили створы шлюзов, оптимизировали ламинарное течение "
            "сетевых пакетов, избавились от любых паразитных завихрений интерфейса и внедрили "
            "бронебойную изоляцию сетевых каналов. Ваши данные текут быстро, стабильно и абсолютно свободно!"
        )

    def _generate_alerts(self) -> str:
        return (
            "> [!NOTE]\n"
            "> **Бесшовное обновление плотины**:\n"
            "> Все ваши настройки, сохранённые профили, персональные ссылки подписок и ключи доступа "
            "сохраняются в полной неприкосновенности. Никаких повторных настроек не требуется как в установленной, "
            "так и в переносимой (Portable) версии программы.\n"
            ">\n"
            "> [!TIP]\n"
            "> **Быстрый доступ к Личному кабинету**:\n"
            "> Больше не нужно вспоминать адрес сервера — кнопка прямого перехода в Личный кабинет «🌐 Личный кабинет ↗» "
            "теперь выведена на верхнюю панель управления, в диалог подписки и в информационные баннеры плотины."
        )

    def _generate_highlights(self) -> str:
        """Формирует визитку главных новшеств в зависимости от версии."""
        if self.version == "1.1.1":
            return (
                "### 🎯 Ключевые инженерные решения версии 1.1.1\n\n"
                "- 🎨 **Безупречный Responsive Card Layout (Интерфейс плотины)**:\n"
                "  Полностью устранены графические артефакты теней и обрезание кнопок («Подключить/Отключить», "
                "шестерёнка, контекстное меню) при любых масштабах экрана Windows (100%, 125%, 150%) "
                "и узких размерах окна.\n\n"
                "- 🔑 **Расширенный центр подписок & Автоопределение Личного кабинета**:\n"
                "  Добавление и редактирование персональной ссылки прямо в окне без правки файлов. "
                "Умное распознавание домена личного кабинета из серверов подписки и гармоничное "
                "расположение кнопок управления без взаимных наложений.\n\n"
                "- ⚡ **Выделенные Wintun-каналы (`bobr0` / `bobr1`, `awg0` / `awg1`) & Бобровый сборщик мусора**:\n"
                "  Двухканальная ротация Ping-Pong при переподключении исключает конфликты сетевого драйвера ОС. "
                "Фоновый сборщик мусора точечно зачищает подвисшие узлы `SWD\\WINTUN`, не задевая чужие VPN.\n\n"
                "- 🚀 **Асинхронный быстрый сетевой стек (0 мс задержки)**:\n"
                "  Ликвидированы тяжелые синхронные вызовы PowerShell. Нативные Win32 API проверки в оперативной "
                "памяти гарантируют мгновенный отклик UI и штатную доставку сигналов закрытия сессий (`CTRL_BREAK_EVENT`, `AnyConnect BYE`).\n\n"
                "- 🛡️ **Бронебойный Single-Instance между Portable и Администратором**:\n"
                "  Сквозной единый глобальный мьютекс и IPC через открытый дескриптор безопасности SDDL/NULL-DACL "
                "гарантируют взаимное распознавание процессов разного уровня привилегий и безопасный обход барьера UIPI."
            )
        elif self.version == "1.1.0":
            return (
                "### 🎯 Ключевые инженерные решения версии 1.1.0\n\n"
                "- 🔑 **Централизованный импорт подписок BobrDobr VPN** по одной персональной ссылке.\n"
                "- ❄️ **Морозный визуальный статус** и блокировка недоступных/истекших профилей.\n"
                "- 🛡️ **Камуфляж OpenConnect** с нормализацией скрытых путей `/?{secret}`.\n"
                "- 🪵 **Защита от гонок процессов и падений** при быстром реконнекте."
            )
        return ""

    def _generate_detailed_changelog(self) -> str:
        cleaned_content = self.entry.raw_content
        # Убираем лишние h2 или h3, если они дублируют заголовок
        lines = cleaned_content.splitlines()
        filtered_lines = []
        for line in lines:
            if line.startswith("## "):
                continue
            filtered_lines.append(line)

        body = "\n".join(filtered_lines).strip()
        return (
            "### 📋 Детализированный журнал работ гидроузла\n\n"
            f"{body}\n"
        )

    def _generate_install_guide(self) -> str:
        ver = self.version
        return (
            "### 📦 Руководство по установке и обновлению плотины\n\n"
            f"#### Вариант 1: Переносимая версия (Portable — Единый `.exe`)\n"
            f"1. Скачайте исполняемый файл **`BobrDobr-VPN-v{ver}.exe`** из блока **Assets** ниже.\n"
            "2. Поместите его в любую удобную папку (например, `D:\\Tools\\BobrDobr\\`) или на USB-накопитель.\n"
            "3. Запустите файл. Все профили и защищённые ключи сохраняются в локальном зашифрованном файле настроек.\n\n"
            f"#### Вариант 2: Установленная версия (Installed — Быстрый запуск на HDD/SSD)\n"
            f"1. Запустите скачанный файл **`BobrDobr-VPN-v{ver}.exe`**.\n"
            "2. В главном меню нажмите кнопку **«Установить на ПК»**.\n"
            "3. Приложение развернётся в системный каталог и создаст удобные ярлыки в меню «Пуск» и на рабочем столе.\n"
            "4. *Если программа уже была установлена ранее:* она автоматически предложит применить обновление при запуске.\n\n"
            "#### 🔒 Проверка контрольной суммы (PowerShell)\n"
            "Для проверки целостности загруженного бинарника выполните команду:\n"
            "```powershell\n"
            f"Get-FileHash -Algorithm SHA256 .\\BobrDobr-VPN-v{ver}.exe\n"
            "```"
        )

    def _generate_footer(self) -> str:
        return (
            "---\n\n"
            "🌲 **БобрДобр VPN** — Заповедник цифровой гидроинженерии.\n\n"
            "*«Чистый поток данных, крепкие плотины и никакого застревания брёвен!»* 🦫🪵⚡💧"
        )


def safe_print(text: str) -> None:
    """Безопасный вывод Unicode/UTF-8 в stdout даже при Windows charmap cp1252/cp866."""
    try:
        if hasattr(sys.stdout, "buffer") and sys.stdout.buffer:
            sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")
            sys.stdout.buffer.flush()
        else:
            print(text)
    except Exception:
        try:
            print(text.encode("utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
        except Exception:
            print(text.encode("ascii", errors="replace").decode("ascii"))


def safe_eprint(text: str) -> None:
    """Безопасный вывод Unicode/UTF-8 в stderr."""
    try:
        if hasattr(sys.stderr, "buffer") and sys.stderr.buffer:
            sys.stderr.buffer.write(text.encode("utf-8", errors="replace") + b"\n")
            sys.stderr.buffer.flush()
        else:
            sys.stderr.write(text + "\n")
    except Exception:
        pass


def find_default_changelog() -> str:
    """Ищет CHANGELOG.md в стандартных путях репозитория."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "..", "CHANGELOG.md"),
        os.path.join(script_dir, "CHANGELOG.md"),
        os.path.join(os.getcwd(), "CHANGELOG.md"),
    ]
    for c in candidates:
        norm = os.path.normpath(c)
        if os.path.isfile(norm):
            return norm
    return os.path.normpath(candidates[0])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Генератор описаний релизов BobrDobr VPN для GitHub Releases.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры использования:\n"
            "  python scripts/generate_release_notes.py --version 1.1.1\n"
            "  python scripts/generate_release_notes.py --version latest -o RELEASE_NOTES.md\n"
            "  python scripts/generate_release_notes.py --version 1.1.1 --title-only\n"
            "  python scripts/generate_release_notes.py --list-versions\n"
        ),
    )

    parser.add_argument(
        "-v",
        "--version",
        default="latest",
        help="Версия для генерации (например, 1.1.1, v1.1.1 или latest). По умолчанию: latest.",
    )
    parser.add_argument(
        "-c",
        "--changelog",
        default=None,
        help="Путь к файлу CHANGELOG.md (по умолчанию ищется в корне репозитория).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Путь к файлу для сохранения Markdown-документа. Если не указан — вывод в stdout.",
    )
    parser.add_argument(
        "--title-only",
        action="store_true",
        help="Вывести только строку названия релиза (удобно для флага --title в gh release create).",
    )
    parser.add_argument(
        "--notes-only",
        action="store_true",
        help="Вывести только тело заметок без верхнего заголовка # (удобно для передачи в --notes-file).",
    )
    parser.add_argument(
        "-l",
        "--list-versions",
        action="store_true",
        help="Вывести список всех обнаруженных в CHANGELOG.md версий и завершить работу.",
    )

    args = parser.parse_args()

    changelog_path = args.changelog or find_default_changelog()
    if not os.path.isfile(changelog_path):
        safe_eprint(f"❌ Ошибка: файл CHANGELOG.md не найден по пути: {changelog_path}")
        return 1

    try:
        changelog = ChangelogParser(changelog_path)
    except Exception as exc:
        safe_eprint(f"❌ Ошибка при чтении CHANGELOG.md: {exc}")
        return 1

    if args.list_versions:
        versions = changelog.list_versions()
        safe_print("Доступные версии в CHANGELOG.md:")
        for ver in versions:
            safe_print(f"  - {ver}")
        return 0

    entry = changelog.get_entry(args.version)
    if not entry:
        safe_eprint(
            f"❌ Ошибка: версия '{args.version}' не найдена в {changelog_path}.\n"
            f"Доступные версии: {', '.join(changelog.list_versions())}"
        )
        return 1

    builder = BobrReleaseNotesBuilder(entry)

    if args.title_only:
        safe_print(builder.get_title())
        return 0

    markdown_text = builder.build_markdown(include_title=not args.notes_only)

    if args.output:
        out_path = os.path.abspath(args.output)
        try:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            safe_eprint(f"✔ Описание релиза v{entry.version} успешно сохранено: {out_path}")
        except Exception as exc:
            safe_eprint(f"❌ Не удалось записать файл {out_path}: {exc}")
            return 1
    else:
        safe_print(markdown_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
