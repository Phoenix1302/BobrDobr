from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QFrame, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QIcon, QDesktopServices
from utils.installer_helper import (
    get_install_dir, install_to_system, update_system_installation,
    has_installed_version, revert_to_portable, full_system_uninstall
)
from utils.version import APP_VERSION, GITHUB_REPO
from utils.platform_helper import is_admin, is_windows


class InstallDialog(QDialog):
    """Dialog confirming installation of BobrDobr to user system directory."""

    def __init__(self, parent=None, app_icon: QIcon = None):
        super().__init__(parent)
        self.setWindowTitle("Установка БобрДобр на ПК")
        if app_icon:
            self.setWindowIcon(app_icon)
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # Header
        title = QLabel("Установка в систему Windows")
        title.setStyleSheet("font-size: 17px; font-weight: 800; color: #d97706;")
        layout.addWidget(title)

        desc = QLabel(
            "БобрДобр будет скопирован в каталог приложений вашей учетной записи, "
            "а на Рабочем столе и в меню «Пуск» появятся удобные ярлыки для запуска."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.4;")
        layout.addWidget(desc)

        # Details box
        box = QFrame()
        box.setStyleSheet("background-color: #182226; border: 1px solid #283941; border-radius: 8px; padding: 12px;")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(8)

        lbl_dir = QLabel(f"<b>Каталог установки:</b> {get_install_dir()}")
        lbl_dir.setStyleSheet("color: #94a3b8; font-size: 12px;")
        lbl_dir.setWordWrap(True)
        box_layout.addWidget(lbl_dir)

        lbl_sh1 = QLabel("✓ Создать ярлык на Рабочем столе")
        lbl_sh1.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 600;")
        box_layout.addWidget(lbl_sh1)

        lbl_sh2 = QLabel("✓ Добавить в меню «Пуск»")
        lbl_sh2.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 600;")
        box_layout.addWidget(lbl_sh2)

        layout.addWidget(box)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_install = QPushButton("Установить на ПК")
        btn_install.setObjectName("btn_primary")
        btn_install.setCursor(Qt.PointingHandCursor)
        btn_install.clicked.connect(self._do_install)
        btn_layout.addWidget(btn_install)

        layout.addLayout(btn_layout)

    def _do_install(self):
        if is_windows() and not is_admin():
            QMessageBox.warning(
                self,
                "Ограничение прав",
                "Установка программы в систему возможна только при запуске от имени администратора.\n\n"
                "Пожалуйста, перезапустите БобрДобр с правами администратора."
            )
            return

        success, msg = install_to_system()
        if success:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Установка завершена")
            msg_box.setText(
                "БобрДобр успешно установлен на ваш компьютер!\n\n"
                "Ярлыки созданы на Рабочем столе и в меню «Пуск».\n\n"
                "Запустить установленную версию прямо сейчас?"
            )
            msg_box.setIcon(QMessageBox.Question)
            btn_launch = msg_box.addButton("Запустить", QMessageBox.YesRole)
            btn_later = msg_box.addButton("Позже", QMessageBox.NoRole)
            msg_box.setDefaultButton(btn_launch)
            msg_box.exec()
            if msg_box.clickedButton() == btn_launch:
                import subprocess
                try:
                    subprocess.Popen([msg])
                    QApplication.instance().quit()
                except Exception:
                    pass
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Ошибка установки",
                f"Не удалось установить программу:\n{msg}"
            )


class UpdateDialog(QDialog):
    """Dialog confirming clean update of installed BobrDobr with profile migration."""

    def __init__(self, parent=None, app_icon: QIcon = None):
        super().__init__(parent)
        self.setWindowTitle("Обновление БобрДобр на ПК")
        if app_icon:
            self.setWindowIcon(app_icon)
        self.setMinimumWidth(500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # Header
        title = QLabel("Обновление установленной версии")
        title.setStyleSheet("font-size: 17px; font-weight: 800; color: #d97706;")
        layout.addWidget(title)

        from utils.version import APP_VERSION
        from utils.config_store import settings
        prof_count = len(settings.get_profiles())

        desc = QLabel(
            f"На вашем компьютере обнаружена установленная версия БобрДобр.\n"
            f"Будет выполнено чистое обновление программы до версии {APP_VERSION}."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.4;")
        layout.addWidget(desc)

        # Details box
        box = QFrame()
        box.setStyleSheet("background-color: #182226; border: 1px solid #283941; border-radius: 8px; padding: 14px;")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(8)

        lbl_dir = QLabel(f"<b>Каталог установки:</b> {get_install_dir()}")
        lbl_dir.setStyleSheet("color: #94a3b8; font-size: 12px;")
        lbl_dir.setWordWrap(True)
        box_layout.addWidget(lbl_dir)

        lbl_sh1 = QLabel(f"✓ Сохранить и перенести подключения: {prof_count} шт.")
        lbl_sh1.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 700;")
        box_layout.addWidget(lbl_sh1)

        lbl_sh2 = QLabel("✓ Чистая установка: сброс системных настроек в эталонный стандарт")
        lbl_sh2.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 600;")
        box_layout.addWidget(lbl_sh2)

        lbl_sh3 = QLabel("✓ Обновить ярлыки на Рабочем столе и в меню «Пуск»")
        lbl_sh3.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 600;")
        box_layout.addWidget(lbl_sh3)

        layout.addWidget(box)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_cleanup = QPushButton("🗑 Удалить с ПК")
        btn_cleanup.setObjectName("btn_destructive")
        btn_cleanup.setCursor(Qt.PointingHandCursor)
        btn_cleanup.setToolTip("Полностью удалить установленную копию из системы и вернуть статус чистой системы.")
        btn_cleanup.clicked.connect(self._do_remove_installed)
        btn_layout.addWidget(btn_cleanup)

        btn_update = QPushButton("🔄 Обновить версию")
        btn_update.setObjectName("btn_primary")
        btn_update.setCursor(Qt.PointingHandCursor)
        btn_update.clicked.connect(self._do_update)
        btn_layout.addWidget(btn_update)

        layout.addLayout(btn_layout)

    def _do_remove_installed(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Удаление установленной версии")
        msg_box.setText(
            "Вы действительно хотите удалить установленную версию БобрДобр с этого ПК?\n\n"
            "Файлы программы в системе и ярлыки будут удалены. Ваши профили в портативной версии останутся сохранены."
        )
        msg_box.setIcon(QMessageBox.Question)
        btn_del = msg_box.addButton("Удалить с ПК", QMessageBox.YesRole)
        btn_del.setObjectName("btn_destructive")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_cancel = msg_box.addButton("Отмена", QMessageBox.NoRole)
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        msg_box.setDefaultButton(btn_cancel)
        msg_box.exec()
        if msg_box.clickedButton() == btn_del:
            from utils.installer_helper import (
                kill_installed_processes, get_install_dir,
                get_desktop_shortcut_path, get_start_menu_shortcut_path,
                schedule_self_delete
            )
            kill_installed_processes()
            install_dir = get_install_dir()
            try:
                for lnk in [get_desktop_shortcut_path(), get_start_menu_shortcut_path()]:
                    if os.path.isfile(lnk):
                        try:
                            os.remove(lnk)
                        except Exception:
                            pass
                if os.path.isdir(install_dir):
                    shutil.rmtree(install_dir, ignore_errors=True)
                if os.path.exists(install_dir):
                    subprocess.run(["cmd.exe", "/c", f'rd /s /q "{install_dir}"'], capture_output=True)
                if os.path.exists(install_dir):
                    schedule_self_delete(install_dir)
            except Exception as e:
                print(f"Cleanup error: {e}")

            # Also remove installed settings.json so Roaming is pure portable
            try:
                from utils.config_store import get_installed_config_path
                inst_cfg = get_installed_config_path()
                if os.path.isfile(inst_cfg):
                    os.remove(inst_cfg)
            except Exception:
                pass

            QMessageBox.information(
                self,
                "Удаление завершено",
                "Установленная версия успешно удалена с компьютера.\n"
                "Теперь используется только портативная версия."
            )
            self.accept()

    def _do_update(self):
        if is_windows() and not is_admin():
            QMessageBox.warning(
                self,
                "Ограничение прав",
                "Обновление программы в системе возможно только при запуске от имени администратора.\n\n"
                "Пожалуйста, перезапустите БобрДобр с правами администратора."
            )
            return

        success, msg, count = update_system_installation()
        if success:
            from utils.version import APP_VERSION
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Обновление завершено")
            msg_box.setText(
                f"БобрДобр успешно обновлен до версии {APP_VERSION}!\n\n"
                f"Выполнена чистая установка: все подключения ({count} шт.) сохранены и перенесены в новый стандарт.\n\n"
                f"Запустить обновленную версию прямо сейчас?"
            )
            msg_box.setIcon(QMessageBox.Information)
            btn_launch = msg_box.addButton("Запустить", QMessageBox.YesRole)
            btn_later = msg_box.addButton("Позже", QMessageBox.NoRole)
            msg_box.setDefaultButton(btn_launch)
            msg_box.exec()
            if msg_box.clickedButton() == btn_launch:
                import subprocess
                try:
                    subprocess.Popen([msg])
                    QApplication.instance().quit()
                except Exception:
                    pass
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Ошибка обновления",
                f"Не удалось обновить программу:\n{msg}"
            )


class UninstallDialog(QDialog):
    """Dialog allowing user to choose between Revert to Portable or Full System Cleanup."""

    def __init__(self, parent=None, app_icon: QIcon = None):
        super().__init__(parent)
        self.setWindowTitle("Управление установкой БобрДобр")
        if app_icon:
            self.setWindowIcon(app_icon)
        self.setMinimumWidth(500)
        self.setModal(True)

        self.selected_action = None  # "portable" or "uninstall"

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel("Управление установленной программой")
        title.setStyleSheet("font-size: 17px; font-weight: 800; color: #d97706;")
        layout.addWidget(title)

        subtitle = QLabel("БобрДобр установлен на этом компьютере. Выберите нужное действие:")
        subtitle.setStyleSheet("color: #cbd5e1; font-size: 13px;")
        layout.addWidget(subtitle)

        # Options Container
        self.btn_group = QButtonGroup(self)

        # Option 1: Revert to Portable
        self.rb_portable = QRadioButton("Вернуть в Portable-режим")
        self.rb_portable.setChecked(True)
        self.rb_portable.setCursor(Qt.PointingHandCursor)
        self.rb_portable.setStyleSheet("font-size: 14px; font-weight: 700; color: #38bdf8;")
        self.btn_group.addButton(self.rb_portable, 1)
        layout.addWidget(self.rb_portable)

        desc_portable = QLabel(
            "Скопирует свежий <b>BobrDobr-VPN.exe</b> в вашу папку «Загрузки» и удалит ярлыки с Рабочего стола и меню «Пуск». "
            "Ваши профили подключений и настройки останутся нетронутыми."
        )
        desc_portable.setWordWrap(True)
        desc_portable.setStyleSheet("color: #94a3b8; font-size: 12px; margin-left: 24px;")
        layout.addWidget(desc_portable)

        # Option 2: Full System Cleanup
        self.rb_full = QRadioButton("Полная очистка системы (Удалить БобрДобр)")
        self.rb_full.setCursor(Qt.PointingHandCursor)
        self.rb_full.setStyleSheet("font-size: 14px; font-weight: 700; color: #f87171;")
        self.btn_group.addButton(self.rb_full, 2)
        layout.addWidget(self.rb_full)

        desc_full = QLabel(
            "Полностью удалит БобрДобр с компьютера: удалит ярлыки, сетевые службы, "
            "фантомные адаптеры Wintun, правила брандмауэра и файл сохранённых настроек."
        )
        desc_full.setWordWrap(True)
        desc_full.setStyleSheet("color: #94a3b8; font-size: 12px; margin-left: 24px;")
        layout.addWidget(desc_full)

        layout.addSpacing(8)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_confirm = QPushButton("Применить")
        self.btn_confirm.setObjectName("btn_primary")
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.clicked.connect(self._do_action)
        btn_layout.addWidget(self.btn_confirm)

        layout.addLayout(btn_layout)

    def _do_action(self):
        if self.rb_portable.isChecked():
            self.selected_action = "portable"
            success, msg = revert_to_portable()
            if success:
                QMessageBox.information(
                    self,
                    "Перевод в Portable режим",
                    f"Программа переведена в портативный режим!\n\n"
                    f"Исполняемый файл создан в:\n{msg}\n\n"
                    f"Ярлыки удалены. При закрытии установленная копия будет очищена."
                )
                self.accept()
            else:
                QMessageBox.warning(self, "Ошибка", f"Не удалось выполнить перевод:\n{msg}")

        elif self.rb_full.isChecked():
            # Confirm destructive action with neat custom buttons
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Подтверждение удаления")
            msg_box.setText(
                "Вы уверены, что хотите полностью стереть БобрДобр с компьютера?\n\n"
                "Все сохраненные профили и настройки VPN будут безвозвратно удалены."
            )
            msg_box.setIcon(QMessageBox.Question)
            btn_del = msg_box.addButton("Удалить всё", QMessageBox.YesRole)
            btn_del.setObjectName("btn_destructive")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_cancel = msg_box.addButton("Отмена", QMessageBox.NoRole)
            btn_cancel.setObjectName("btn_secondary")
            btn_cancel.setCursor(Qt.PointingHandCursor)
            msg_box.setDefaultButton(btn_cancel)
            msg_box.exec()
            if msg_box.clickedButton() == btn_del:
                self.selected_action = "uninstall"
                success, msg = full_system_uninstall()
                if success:
                    QMessageBox.information(
                        self,
                        "Очистка завершена",
                        "Все файлы программы, настройки и сетевые службы удалены.\n"
                        "Приложение завершает работу."
                    )
                    self.accept()
                else:
                    QMessageBox.warning(self, "Ошибка", f"Не удалось полностью удалить программу:\n{msg}")


class GitHubUpdateDialog(QDialog):
    """Dialog notifying about a new version on GitHub and offering to open release / download."""

    def __init__(self, parent=None, update_info: dict = None, app_icon: QIcon = None):
        super().__init__(parent)
        self.setWindowTitle("Обновление БобрДобр")
        if app_icon:
            self.setWindowIcon(app_icon)
        self.setMinimumWidth(520)
        self.setModal(True)
        self.update_info = update_info or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # Header
        title = QLabel("🚀 Доступна новая версия БобрДобр!")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #d97706;")
        layout.addWidget(title)

        curr_ver = self.update_info.get("current_version", APP_VERSION)
        new_ver = self.update_info.get("latest_version", APP_VERSION)
        rel_name = self.update_info.get("release_name", f"БобрДобр v{new_ver}")

        desc = QLabel(
            "На GitHub опубликован новый релиз приложения. "
            "Рекомендуется обновиться для получения актуальных улучшений и исправлений."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.4;")
        layout.addWidget(desc)

        # Version comparison card
        box = QFrame()
        box.setStyleSheet("background-color: #182226; border: 1px solid #283941; border-radius: 10px; padding: 14px;")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(10)

        row_ver = QHBoxLayout()
        row_ver.setSpacing(10)

        lbl_c_tag = QLabel(f"Текущая: v{curr_ver}")
        lbl_c_tag.setStyleSheet(
            "background-color: #24343b; color: #94a3b8; font-weight: 700; "
            "border: 1px solid #334852; border-radius: 6px; padding: 4px 10px; font-size: 12px;"
        )
        row_ver.addWidget(lbl_c_tag)

        arrow = QLabel("➔")
        arrow.setStyleSheet("color: #d97706; font-size: 15px; font-weight: 800;")
        row_ver.addWidget(arrow)

        lbl_n_tag = QLabel(f"Новая версия: v{new_ver}")
        lbl_n_tag.setStyleSheet(
            "background-color: rgba(16, 185, 129, 0.15); color: #34d399; font-weight: 800; "
            "border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 6px; padding: 4px 10px; font-size: 12px;"
        )
        row_ver.addWidget(lbl_n_tag)
        row_ver.addStretch()
        box_layout.addLayout(row_ver)

        lbl_rel_title = QLabel(f"<b>Релиз:</b> {rel_name}")
        lbl_rel_title.setStyleSheet("color: #f1f5f9; font-size: 13px;")
        lbl_rel_title.setWordWrap(True)
        box_layout.addWidget(lbl_rel_title)

        # Body / Notes if available
        body_text = self.update_info.get("body", "").strip()
        if body_text:
            lbl_notes_title = QLabel("Список изменений:")
            lbl_notes_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 700;")
            box_layout.addWidget(lbl_notes_title)

            notes_frame = QFrame()
            notes_frame.setStyleSheet("background-color: #12191d; border: 1px solid #1f2b31; border-radius: 6px; padding: 8px;")
            notes_layout = QVBoxLayout(notes_frame)
            notes_layout.setContentsMargins(6, 6, 6, 6)

            lbl_body = QLabel(body_text[:400] + ("..." if len(body_text) > 400 else ""))
            lbl_body.setWordWrap(True)
            lbl_body.setStyleSheet("color: #cbd5e1; font-size: 11px;")
            notes_layout.addWidget(lbl_body)
            box_layout.addWidget(notes_frame)

        layout.addWidget(box)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_later = QPushButton("Напомнить позже")
        btn_later.setObjectName("btn_secondary")
        btn_later.setCursor(Qt.PointingHandCursor)
        btn_later.clicked.connect(self.reject)
        btn_layout.addWidget(btn_later)

        btn_open = QPushButton("🚀 Перейти к загрузке релиза")
        btn_open.setObjectName("btn_primary")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.clicked.connect(self._open_release)
        btn_layout.addWidget(btn_open)

        layout.addLayout(btn_layout)

    def _open_release(self):
        target_url = self.update_info.get("release_url") or f"https://github.com/{GITHUB_REPO}/releases"
        try:
            QDesktopServices.openUrl(QUrl(target_url))
        except Exception:
            import webbrowser
            webbrowser.open(target_url)
        self.accept()

