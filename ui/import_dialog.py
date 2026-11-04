from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit,
)

from data_sources.connector import ArchiveSource
from data_sources.importer import import_file
from database.store import Store


class ImportWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.completed.emit(self.operation())
        except Exception as error:
            import logging
            logging.exception("Importazione fallita")
            self.failed.emit(str(error) if isinstance(error, ValueError) else
                             "Operazione fallita. Verificare dipendenze, rete e registro applicativo.")


class ImportDialog(QDialog):
    def __init__(self, store: Store, parent):
        super().__init__(parent)
        self.store = store
        self.worker = None
        self.setWindowTitle("Importa o aggiorna archivio")
        self.resize(650, 510)
        form = QFormLayout(self)
        note = QLabel("Importazione parziale: le righe valide vengono salvate; quelle errate "
                      "sono riportate nel registro. Formato normalizzato descritto nel README. "
                      "Nessuna fonte ufficiale preconfigurata.")
        note.setWordWrap(True)
        form.addRow(note)
        self.synthetic = QCheckBox("Il file locale contiene dati sintetici")
        form.addRow(self.synthetic)
        self.file_button = QPushButton("Scegli file CSV, Excel o JSON…")
        self.file_button.clicked.connect(self.choose_file)
        form.addRow(self.file_button)
        self.url = QLineEdit()
        self.url.setPlaceholderText("URL HTTPS di un archivio autorizzato")
        form.addRow("Fonte remota", self.url)
        self.format = QComboBox()
        self.format.addItems(["csv", "json", "xlsx"])
        form.addRow("Formato remoto", self.format)
        self.authorized = QCheckBox("Ho verificato che il download da questa fonte è consentito")
        form.addRow(self.authorized)
        self.download_button = QPushButton("Aggiorna da fonte remota")
        self.download_button.clicked.connect(self.download)
        form.addRow(self.download_button)
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        form.addRow(self.result)
        close = QPushButton("Chiudi")
        close.clicked.connect(self.reject)
        form.addRow(close)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Archivio estrazioni", "", "Archivi (*.csv *.xlsx *.json)")
        if path:
            synthetic = self.synthetic.isChecked()
            self.start(lambda: import_file(self.store, Path(path), synthetic))

    def download(self):
        if not self.authorized.isChecked():
            self.result.setPlainText("Confermare che la fonte consente il download.")
            return
        try:
            source = ArchiveSource(self.url.text().strip(), self.format.currentText())
        except ValueError as error:
            self.result.setPlainText(str(error))
            return
        self.start(lambda: source.update(self.store))

    def start(self, operation):
        if self.worker and self.worker.isRunning():
            return
        self.file_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.result.setPlainText("Operazione in corso…")
        self.worker = ImportWorker(operation, self)
        self.worker.completed.connect(self.completed)
        self.worker.failed.connect(self.result.setPlainText)
        self.worker.finished.connect(self.finished_work)
        self.worker.start()

    def completed(self, report):
        self.result.setPlainText(f"Aggiunte: {report.inserted}\nDuplicate: {report.duplicates}\n"
                                 f"Rifiutate: {report.rejected}\n" + "\n".join(report.errors))

    def finished_work(self):
        self.file_button.setEnabled(True)
        self.download_button.setEnabled(True)

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.result.append("Attendere il termine dell'operazione prima di chiudere.")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
