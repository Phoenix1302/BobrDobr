"""
End-to-End Startup Smoke Test for BobrDobr VPN.
Ensures that main.py and the full main() entrypoint initialize QApplication,
window icons, Fusion palettes, single-instance checks, and MainWindow
without UnboundLocalError, NameError, or unhandled exceptions.
"""

import os
import sys
import unittest
from unittest.mock import patch

# Ensure headless offscreen platform for Qt
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


class TestMainApplicationStartup(unittest.TestCase):
    """Verifies that the entire main() application bootstrapping sequence runs cleanly."""

    @patch("utils.single_instance.handle_startup_single_instance", return_value=True)
    def test_main_gui_bootstrapping_smoke(self, mock_single_instance):
        """
        Executes main() with patched sys.argv (clean GUI launch) and an immediate
        singleShot quit event to verify the complete bootstrapping path:
        icon resolution, Fusion palette setup, stylesheet parsing, and MainWindow creation.
        """
        import main
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        # Ensure sys.argv has no CLI flags
        orig_argv = sys.argv
        sys.argv = [os.path.join(SRC_DIR, "main.py")]

        # Schedule immediate quit as soon as the event loop enters
        def schedule_quit():
            app = QApplication.instance()
            if app:
                QTimer.singleShot(50, app.quit)

        # Patch app.exec to quit cleanly and patch os._exit to capture clean exit code
        exit_code_captured = []
        with patch.object(main.os, "_exit", side_effect=lambda code: exit_code_captured.append(code)), \
             patch("sys.exit", side_effect=lambda code: exit_code_captured.append(code)):

            # Post quit timer right after app is created
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(schedule_quit)

            # We hook QApplication.__init__ or schedule before exec
            orig_exec = QApplication.exec
            def mock_exec(*args, **kwargs):
                schedule_quit()
                return orig_exec(*args, **kwargs)

            with patch.object(QApplication, "exec", side_effect=mock_exec):
                try:
                    main.main()
                except SystemExit:
                    pass
                finally:
                    sys.argv = orig_argv

        # If any UnboundLocalError or startup exception occurred, main() would have crashed before capturing exit
        self.assertTrue(len(exit_code_captured) > 0, "main() did not exit cleanly through os._exit or sys.exit")
        self.assertEqual(exit_code_captured[0], 0, f"main() exited with non-zero code {exit_code_captured[0]}")


if __name__ == "__main__":
    unittest.main()
