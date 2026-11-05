#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for BobrDobr VPN Release Notes Generator (scripts/generate_release_notes.py).
"""

import os
import subprocess
import sys
import unittest

# Ensure repo root and scripts are in sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from generate_release_notes import (
    ChangelogParser, BobrReleaseNotesBuilder, find_default_changelog
)


class TestReleaseNotesGenerator(unittest.TestCase):
    """Тестирование парсинга и генерации описаний релизов."""

    @classmethod
    def setUpClass(cls):
        cls.changelog_path = find_default_changelog()
        cls.parser = ChangelogParser(cls.changelog_path)

    def test_changelog_exists_and_parses(self):
        """Проверяет существование и корректный парсинг CHANGELOG.md."""
        self.assertTrue(os.path.isfile(self.changelog_path))
        versions = self.parser.list_versions()
        self.assertIn("1.1.1", versions)
        self.assertIn("1.1.0", versions)
        self.assertIn("1.0.13", versions)

    def test_version_latest_resolution(self):
        """Проверяет получение последней (актуальной) версии."""
        entry = self.parser.get_entry("latest")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.version, "1.1.1")

    def test_version_1_1_1_details(self):
        """Проверяет наличие всех 5 ключевых требований в заметках v1.1.1."""
        entry = self.parser.get_entry("1.1.1")
        self.assertIsNotNone(entry)
        builder = BobrReleaseNotesBuilder(entry)
        markdown = builder.build_markdown()

        # 1. Заголовок и метаданные
        self.assertIn("🦫 БобрДобр VPN v1.1.1", markdown)
        self.assertIn("Инженерный апгрейд плотины & Быстрый сетевой шлюз", markdown)

        # 2. GitHub-алерты
        self.assertIn("> [!NOTE]", markdown)
        self.assertIn("> [!TIP]", markdown)

        # 3. Полное устранение графических артефактов и обрезания кнопок (Responsive Card Layout)
        self.assertIn("Responsive Card Layout", markdown)
        self.assertIn("обрезание кнопок", markdown)

        # 4. Расширенный центр подписок и автоопределение Личного кабинета
        self.assertIn("Расширенный центр подписок", markdown)
        self.assertIn("Личного кабинета", markdown)

        # 5. Выделенные адаптеры Wintun (bobr0 / bobr1) и фоновый сборщик
        self.assertIn("bobr0", markdown)
        self.assertIn("bobr1", markdown)
        self.assertIn("Wintun", markdown)
        self.assertIn("сборщик", markdown)

        # 6. Асинхронный быстрый сетевой стек (0 мс задержки)
        self.assertIn("Асинхронный быстрый сетевой стек", markdown)
        self.assertIn("0 мс", markdown)

        # 7. Бесшовная защита от повторного запуска (Single-Instance / SDDL / UIPI)
        self.assertIn("Single-Instance", markdown)
        self.assertIn("SDDL", markdown)
        self.assertIn("UIPI", markdown)

        # 8. Инструкция по установке и обновлению
        self.assertIn("Руководство по установке и обновлению плотины", markdown)
        self.assertIn("BobrDobr-VPN-v1.1.1.exe", markdown)
        self.assertIn("SHA256", markdown)

    def test_title_only_flag(self):
        """Проверяет генерацию только заголовка релиза."""
        entry = self.parser.get_entry("1.1.1")
        builder = BobrReleaseNotesBuilder(entry)
        title = builder.get_title()
        self.assertTrue(title.startswith("🦫 БобрДобр VPN v1.1.1"))
        self.assertIn("Инженерный апгрейд плотины", title)

    def test_cli_execution(self):
        """Проверяет вызов скрипта через командную строку."""
        script_path = os.path.join(SCRIPTS_DIR, "generate_release_notes.py")
        res = subprocess.run(
            [sys.executable, script_path, "--version", "1.1.1", "--title-only"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("🦫 БобрДобр VPN v1.1.1", res.stdout)

        # Проверка флага --list-versions
        res_list = subprocess.run(
            [sys.executable, script_path, "--list-versions"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(res_list.returncode, 0)
        self.assertIn("1.1.1", res_list.stdout)
        self.assertIn("1.1.0", res_list.stdout)


if __name__ == "__main__":
    unittest.main()
