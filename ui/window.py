import json
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from database.store import Store
from games.models import Draw

STYLE = """
QWidget { background: #101827; color: #e5edf9; font-size: 14px; }
QListWidget { background: #172339; border: none; min-width: 210px; }
QListWidget::item { padding: 14px; }
QListWidget::item:selected { background: #2456a6; }
QPushButton { background: #2563bc; padding: 10px; border-radius: 5px; }
QPushButton:hover { background: #3278df; }
QLineEdit, QComboBox, QSpinBox, QTextEdit { background: #1d2b43; padding: 6px; }
QHeaderView::section { background: #243756; padding: 8px; }
QTableWidget { gridline-color: #293a55; }
QLabel#heading { font-size: 26px; font-weight: bold; }
"""


class DrawDialog(QDialog):
    def __init__(self, store: Store, parent: QWidget):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Inserimento manuale estrazione")
        self.resize(540, 440)
        form = QFormLayout(self)
        self.rule = QComboBox()
        for key in store.rules.rules:
            self.rule.addItem(" / ".join(key), key)
        self.wheel = QComboBox()
        self.identifier = QLineEdit()
        self.date = QLineEdit()
        self.date.setPlaceholderText("2026-01-02T20:00:00+01:00")
        self.numbers = QLineEdit()
        self.numbers.setPlaceholderText("Numeri separati da spazi")
        self.extras = QLineEdit("{}")
        self.source = QLineEdit("manuale")
        self.synthetic = QCheckBox("Dati sintetici (archivio separato)")
        for title, widget in (("Gioco / variante", self.rule), ("Ruota", self.wheel),
                              ("Identificativo", self.identifier), ("Data ISO con fuso", self.date),
                              ("Numeri estratti", self.numbers), ("Extra (JSON)", self.extras),
                              ("Fonte", self.source), ("Tipo dati", self.synthetic)):
            form.addRow(title, widget)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        form.addRow(self.hint)
        self.rule.currentIndexChanged.connect(self.update_rule)
        self.update_rule()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def update_rule(self):
        rule = self.store.rules.rules[self.rule.currentData()]
        self.wheel.clear()
        self.wheel.addItems(rule["wheels"] or [""])
        self.extras.setText(json.dumps({key: None for key in rule["extras"]}))
        self.hint.setText(f"{rule['count']} numeri distinti da {rule['minimum']} a {rule['maximum']}. "
                          "Regola preliminare: verifica ufficiale ancora necessaria. Extra richiesti: "
                          + (", ".join(rule["extras"]) or "nessuno"))

    def save(self):
        try:
            game, variant = self.rule.currentData()
            extras = json.loads(self.extras.text())
            if not isinstance(extras, dict):
                raise ValueError("Gli extra devono essere un oggetto JSON")
            draw = Draw(game, variant, self.identifier.text().strip(),
                        datetime.fromisoformat(self.date.text().strip()),
                        tuple(int(n) for n in self.numbers.text().replace(",", " ").split()),
                        self.wheel.currentText(), extras, self.synthetic.isChecked(), self.source.text().strip())
            added = self.store.add_draw(draw)
            if not added:
                QMessageBox.information(self, "Duplicato", "Estrazione già presente: nessun dato modificato.")
            self.accept()
        except (ValueError, TypeError) as error:
            QMessageBox.warning(self, "Dati non validi", str(error))
        except Exception:
            import logging
            logging.exception("Salvataggio estrazione fallito")
            QMessageBox.critical(self, "Errore", "Salvataggio non riuscito. Consultare il log applicativo.")


class MainWindow(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.setWindowTitle("LottoPredict AI · Archivio e importazione")
        self.resize(1200, 760)
        self.setStyleSheet(STYLE)
        root = QWidget()
        layout = QHBoxLayout(root)
        navigation = QListWidget()
        navigation.addItems(["Dashboard", "Archivio estrazioni", "Analisi statistiche", "Pattern e correlazioni",
                             "AI Prediction Engine", "Generatore combinazioni", "Backtesting",
                             "Confronto algoritmi", "Impostazioni"])
        self.pages = QStackedWidget()
        layout.addWidget(navigation, 1)
        layout.addWidget(self.pages, 5)
        self.setCentralWidget(root)
        dashboard, dashboard_layout = self.page("LottoPredict AI")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        dashboard_layout.addWidget(self.summary)
        notice = QLabel("Le estrazioni sono casuali: nessuna vincita è garantita.\n"
                        "Le frequenze e i ritardi non dimostrano capacità predittiva.\n\n"
                        "Archivio locale, importazione CSV/Excel/JSON, analisi descrittive, simulazioni e modelli sperimentali. "
                        "I risultati dei backtest dipendono dai dati e non garantiscono vincite future.")
        notice.setWordWrap(True)
        dashboard_layout.addWidget(notice)
        dashboard_layout.addStretch()
        self.pages.addWidget(dashboard)
        analysis_button = QPushButton("Apri analisi statistiche e simulazione Monte Carlo")
        analysis_button.clicked.connect(self.open_analysis)
        dashboard_layout.insertWidget(2, analysis_button)
        experiment_button = QPushButton("Previsioni AI, backtesting e confronto algoritmi")
        experiment_button.clicked.connect(self.open_experiments)
        dashboard_layout.insertWidget(3, experiment_button)
        archive, archive_layout = self.page("Archivio estrazioni")
        controls = QHBoxLayout()
        self.game = QComboBox()
        self.game.addItem("Tutti i giochi", None)
        for name in dict.fromkeys(key[0] for key in store.rules.rules):
            self.game.addItem(name, name)
        self.synthetic = QCheckBox("Mostra solo dati sintetici")
        self.limit = QSpinBox()
        self.limit.setRange(1, 100000)
        self.limit.setValue(1000)
        add = QPushButton("Inserisci estrazione")
        add.clicked.connect(self.add_draw)
        for widget in (self.game, self.synthetic, QLabel("Limite:"), self.limit, add):
            controls.addWidget(widget)
        archive_layout.addLayout(controls)
        import_button = QPushButton("Importa file / aggiorna da fonte configurabile")
        import_button.clicked.connect(self.import_archive)
        archive_layout.addWidget(import_button)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Data UTC", "Gioco", "Variante", "Ruota", "ID", "Numeri", "Extra", "Fonte"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        archive_layout.addWidget(self.table)
        self.pages.addWidget(archive)
        settings, settings_layout = self.page("Impostazioni e registro")
        path = QLabel(f"Database locale: {store.path}\n"
                      "Percorso personalizzabile tramite LOTTOPREDICT_DATA_DIR prima dell'avvio.\n"
                      "Le regole predefinite sono preliminari e non ancora verificate presso fonti ufficiali.\n"
                      "Nessuna fonte di download è configurata; nessun archivio reale è incluso.")
        path.setWordWrap(True)
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        settings_layout.addWidget(path)
        self.rule_text = QTextEdit()
        self.rule_text.setReadOnly(True)
        self.rule_text.setPlainText(json.dumps(list(store.rules.rules.values()), indent=2, ensure_ascii=False))
        settings_layout.addWidget(self.rule_text)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        settings_layout.addWidget(self.logs)
        self.pages.addWidget(settings)
        for index, (title, description, action) in enumerate([
            ("Analisi statistiche", "Frequenze, finestre mobili, intervalli Wilson e ritardi. Selezionare una sola serie.", self.open_analysis),
            ("Pattern e correlazioni", "Coppie, terzine, test temporali e cambiamenti di distribuzione. Risultati esplorativi con correzioni multiple.", self.open_analysis),
            ("AI Prediction Engine", "Modelli sperimentali e Monte Carlo. L'ensemble usa validazione cronologica interna e può tornare al caso uniforme.", self.open_experiments),
            ("Generatore combinazioni", "Combinazioni sui numeri principali con punteggi relativi non calibrati. Salvataggio immutabile per estrazioni future.", self.open_experiments),
            ("Backtesting", "Walk-forward con training espansivo o mobile, baseline casuale e frequenze. Parametri da fissare prima del test.", self.open_experiments),
            ("Confronto algoritmi", "Confronto calcolato sui dati selezionati, intervalli descrittivi e test contro il caso. Nessun risultato precalcolato.", self.open_experiments),
        ], start=2):
            page, page_layout = self.page(title)
            details = QLabel(description)
            details.setWordWrap(True)
            page_layout.addWidget(details)
            run = QPushButton("Seleziona dati e avvia")
            run.clicked.connect(action)
            page_layout.addWidget(run)
            page_layout.addStretch()
            self.pages.insertWidget(index, page)
        navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        navigation.setCurrentRow(0)
        self.game.currentIndexChanged.connect(self.refresh)
        self.synthetic.toggled.connect(self.refresh)
        self.limit.valueChanged.connect(self.refresh)
        self.refresh()

    @staticmethod
    def page(title: str):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        heading = QLabel(title)
        heading.setObjectName("heading")
        layout.addWidget(heading)
        return widget, layout

    def add_draw(self):
        if DrawDialog(self.store, self).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def import_archive(self):
        from ui.import_dialog import ImportDialog
        ImportDialog(self.store, self).exec()
        self.refresh()

    def open_analysis(self):
        from ui.analysis_dialog import AnalysisDialog
        AnalysisDialog(self.store, self).exec()

    def open_experiments(self):
        from ui.experiment_dialog import ExperimentDialog
        ExperimentDialog(self.store, self).exec()

    def refresh(self):
        real, synthetic = self.store.count(), self.store.count(True)
        latest = self.store.list_draws(limit=1)
        last = (f"{latest[0]['game']} · {latest[0]['variant']} · {latest[0]['occurred_at']}"
                if latest else "Nessuna estrazione reale disponibile")
        self.summary.setText(f"Estrazioni reali: {real}    |    Sintetiche: {synthetic}\n\nUltima estrazione: {last}")
        rows = self.store.list_draws(self.game.currentData(), self.synthetic.isChecked(), self.limit.value())
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = [row[k] for k in ("occurred_at", "game", "variant", "wheel", "draw_id", "numbers", "extras", "source")]
            for j, value in enumerate(values):
                self.table.setItem(i, j, QTableWidgetItem(str(value)))
        self.table.setSortingEnabled(True)
        self.logs.setPlainText("\n".join(f"{row['created_at']} {row['level']} {row['message']}" for row in self.store.recent_logs()) or "Nessuna operazione registrata.")
