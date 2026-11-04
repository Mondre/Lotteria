import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 non installato: avvio GUI non verificato")
class GuiSmokeTests(unittest.TestCase):
    def test_windows_dialogs_and_manual_insertion(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QDialog
        from database.store import Store
        from games.rules import RuleRegistry
        from ui.window import MainWindow, DrawDialog
        from ui.import_dialog import ImportDialog
        from ui.analysis_dialog import AnalysisDialog
        from ui.experiment_dialog import ExperimentDialog
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "test.sqlite3", RuleRegistry())
            window = MainWindow(store)
            self.assertEqual(window.pages.count(), 9)
            for dialog_class in (ImportDialog, AnalysisDialog, ExperimentDialog):
                dialog = dialog_class(store, window)
                dialog.show()
                app.processEvents()
                dialog.close()
            dialog = DrawDialog(store, window)
            dialog.identifier.setText("gui-test")
            dialog.date.setText("2025-01-01T20:00:00+01:00")
            dialog.numbers.setText("1 2 3 4 5")
            dialog.synthetic.setChecked(True)
            dialog.save()
            self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
            self.assertEqual(store.count(True), 1)
            window.refresh()
            window.close()


if __name__ == "__main__":
    unittest.main()
