from datetime import datetime
import json

from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QSpinBox

from machine_learning.models import MODELS
from ui.analysis_dialog import AnalysisDialog


class ExperimentDialog(AnalysisDialog):
    def __init__(self, store, parent):
        super().__init__(store, parent)
        self.setWindowTitle("Previsioni AI · Backtesting · Confronto algoritmi")
        form = self.layout()
        self.model = QComboBox()
        self.model.addItems(MODELS)
        self.model.setCurrentText("frequency")
        self.combinations = QSpinBox()
        self.combinations.setRange(1, 100)
        self.combinations.setValue(5)
        self.initial = QSpinBox()
        self.initial.setRange(2, 99999)
        self.initial.setValue(700)
        self.train_window = QSpinBox()
        self.train_window.setRange(0, 100000)
        self.train_window.setSpecialValueText("Espansiva")
        self.target_id = QLineEdit()
        self.target_date = QLineEdit()
        self.target_date.setPlaceholderText("Data futura ISO 8601 con fuso")
        for label, widget in reversed([("Modello", self.model), ("Combinazioni", self.combinations),
                                        ("Training iniziale backtest", self.initial), ("Finestra training (0=espansiva)", self.train_window),
                                        ("ID futura estrazione", self.target_id), ("Data futura estrazione", self.target_date)]):
            form.insertRow(6, label, widget)
        self.analyze_button.setText("Genera combinazioni sperimentali")
        self.analyze_button.clicked.disconnect()
        self.analyze_button.clicked.connect(self.generate)
        self.simulate_button.setText("Backtest e confronto con le baseline")
        self.simulate_button.clicked.disconnect()
        self.simulate_button.clicked.connect(self.backtest)
        self.save_button = QPushButton("Salva previsione futura immutabile")
        self.save_button.clicked.connect(self.save)
        self.save_button.setEnabled(False)
        form.addRow(self.save_button)
        history = QPushButton("Mostra storico previsioni e corrispondenze")
        history.clicked.connect(self.history)
        form.addRow(history)
        self.table.hide()

    def selection(self):
        return (*self.rule.currentData(), self.wheel.currentText(), self.synthetic.isChecked(), self.limit.value())

    def generate(self):
        selection = self.selection()
        name, combinations, seed = self.model.currentText(), self.combinations.value(), self.seed.value()
        def operation():
            from predictions.engine import generate
            return generate(self.store.history(*selection), self.store.rules, name, combinations, seed)
        self.start(operation)

    def backtest(self):
        selection = self.selection()
        name, initial, seed = self.model.currentText(), self.initial.value(), self.seed.value()
        window = self.train_window.value() or None
        def operation():
            from backtesting.engine import walk_forward
            return walk_forward(self.store.history(*selection), self.store.rules, (name,), initial, window, seed=seed)
        self.start(operation)

    def start(self, operation):
        self.save_button.setEnabled(False)
        super().start(operation)

    def completed(self, result):
        super().completed(result)
        self.save_button.setEnabled("tickets" in result)

    def save(self):
        if not self.result or "tickets" not in self.result:
            return
        from predictions.engine import save_prediction
        try:
            identifier = save_prediction(self.store, self.result, self.target_id.text(), datetime.fromisoformat(self.target_date.text().strip()))
            self.report.append(f"Previsione salvata e immutabile: {identifier}")
            self.save_button.setEnabled(False)
        except (ValueError, KeyError) as error:
            self.report.append(f"Salvataggio rifiutato: {error}")

    def history(self):
        if self.worker and self.worker.isRunning():
            return
        self.report.setPlainText(json.dumps(self.store.prediction_history(), ensure_ascii=False, indent=2))
