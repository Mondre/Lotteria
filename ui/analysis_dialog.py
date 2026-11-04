import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QLabel,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit,
)

from database.store import Store
from ui.import_dialog import ImportWorker


class AnalysisDialog(QDialog):
    def __init__(self, store: Store, parent):
        super().__init__(parent)
        self.store = store
        self.worker = None
        self.result = None
        self.setWindowTitle("Analisi statistiche e Monte Carlo")
        self.resize(1000, 760)
        form = QFormLayout(self)
        note = QLabel("Statistiche descrittive, non previsioni di vincita. Regole ancora preliminari. "
                      "Frequenza relativa = quota di estrazioni in cui compare il numero. "
                      "Un ritardo alto non aumenta la probabilità della prossima uscita.")
        note.setWordWrap(True)
        form.addRow(note)
        self.rule = QComboBox()
        for key in store.rules.rules:
            self.rule.addItem(" / ".join(key), key)
        self.wheel = QComboBox()
        self.rule.currentIndexChanged.connect(self.update_rule)
        self.update_rule()
        self.limit = QSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(1000)
        self.synthetic = QCheckBox("Usa solo archivio sintetico")
        self.seed = QSpinBox()
        self.seed.setRange(0, 2147483647)
        self.seed.setValue(42)
        for label, widget in (("Gioco / variante", self.rule), ("Ruota", self.wheel),
                              ("Ultime estrazioni", self.limit), ("Tipo dati", self.synthetic), ("Seed simulazione", self.seed)):
            form.addRow(label, widget)
        self.analyze_button = QPushButton("Analizza archivio selezionato")
        self.analyze_button.clicked.connect(self.analyze)
        self.simulate_button = QPushButton("Simula 100.000 estrazioni uniformi")
        self.simulate_button.clicked.connect(self.simulate)
        form.addRow(self.analyze_button, self.simulate_button)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Numero", "Frequenza", "Relativa", "Attesa", "IC 95%", "p Holm", "Ritardo", "Max osservato"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        form.addRow(self.table)
        self.report = QTextEdit()
        self.report.setReadOnly(True)
        form.addRow(self.report)
        self.export_button = QPushButton("Esporta risultato JSON")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export)
        form.addRow(self.export_button)
        self.chart_button = QPushButton("Grafico interattivo")
        self.chart_button.setEnabled(False)
        self.chart_button.clicked.connect(self.chart)
        form.addRow(self.chart_button)

    def update_rule(self):
        self.wheel.clear()
        self.wheel.addItems(self.store.rules.rules[self.rule.currentData()]["wheels"] or [""])

    def analyze(self):
        game, variant = self.rule.currentData()
        wheel, synthetic, limit = self.wheel.currentText(), self.synthetic.isChecked(), self.limit.value()
        def operation():
            from lotto_statistics.engine import analyze
            return analyze(self.store.history(game, variant, wheel, synthetic, limit), self.store.rules)
        self.start(operation)

    def simulate(self):
        game, variant = self.rule.currentData()
        seed = self.seed.value()
        def operation():
            from lotto_statistics.engine import monte_carlo
            return monte_carlo(self.store.rules, game, variant, seed=seed)
        self.start(operation)

    def start(self, operation):
        if self.worker and self.worker.isRunning():
            return
        self.result = None
        self.export_button.setEnabled(False)
        self.chart_button.setEnabled(False)
        self.analyze_button.setEnabled(False)
        self.simulate_button.setEnabled(False)
        self.table.setRowCount(0)
        self.report.setPlainText("Calcolo in corso…")
        self.worker = ImportWorker(operation, self)
        self.worker.completed.connect(self.completed)
        self.worker.failed.connect(self.report.setPlainText)
        self.worker.finished.connect(self.finished_work)
        self.worker.start()

    def finished_work(self):
        self.analyze_button.setEnabled(True)
        self.simulate_button.setEnabled(True)

    def completed(self, result):
        self.result = result
        self.export_button.setEnabled(True)
        self.chart_button.setEnabled(any(key in result for key in ("frequencies", "summary")))
        frequencies = result.get("frequencies", [])
        if frequencies and isinstance(frequencies[0], dict):
            self.table.setSortingEnabled(False)
            self.table.setRowCount(len(frequencies))
            for index, frequency in enumerate(frequencies):
                delay = result["delays"][index]
                values = [frequency["number"], frequency["count"], frequency['relative'],
                          frequency['expected_count'],
                          " – ".join(f"{v:.4f}" for v in frequency["ci95"]),
                          frequency['p_holm'], delay["current"], delay["max_observed"]]
                for column, value in enumerate(values):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.EditRole, value)
                    self.table.setItem(index, column, item)
            self.table.setSortingEnabled(True)
            self.table.resizeColumnsToContents()
        self.report.setPlainText(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))

    def export(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Esporta analisi", "analisi.json", "JSON (*.json)")
        if path:
            try:
                Path(path).write_text(json.dumps(self.result, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
            except OSError as error:
                self.report.append(f"Esportazione fallita: {error}")

    def chart(self):
        if self.result:
            try:
                from ui.chart_dialog import ChartDialog
                ChartDialog(self.result, self).exec()
            except (ImportError, ValueError) as error:
                self.report.append(f"Grafico non disponibile: {error}")

    def reject(self):
        if self.worker and self.worker.isRunning():
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
