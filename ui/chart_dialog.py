from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout


class ChartDialog(QDialog):
    def __init__(self, result, parent):
        super().__init__(parent)
        self.result = result
        self.setWindowTitle("Grafico · zoom, pan ed esportazione")
        self.resize(1100, 700)
        self.layout_box = QVBoxLayout(self)
        self.view = QComboBox()
        self.view.addItem("Frequenze / risultato", "frequencies")
        self.number = QComboBox()
        if "delays" in result:
            self.view.addItem("Ritardi attuali", "delays")
            self.view.addItem("Distribuzione delle somme", "sums")
            if all(row.get("trajectory") for row in result["frequencies"]):
                self.view.addItem("Andamento per numero", "trajectory")
            for row in result["frequencies"]:
                self.number.addItem(str(row["number"]), row["number"])
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Grafico"))
        controls.addWidget(self.view)
        controls.addWidget(self.number)
        self.layout_box.addLayout(controls)
        self.canvas = self.toolbar = None
        self.view.currentIndexChanged.connect(self.redraw)
        self.number.currentIndexChanged.connect(self.redraw)
        self.redraw()

    def redraw(self):
        from visualizations.charts import make_figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
        figure = make_figure(self.result, self.view.currentData(), self.number.currentData())
        for widget in (self.toolbar, self.canvas):
            if widget:
                self.layout_box.removeWidget(widget)
                widget.deleteLater()
        self.canvas = FigureCanvasQTAgg(figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.layout_box.addWidget(self.toolbar)
        self.layout_box.addWidget(self.canvas)
        self.number.setVisible(self.view.currentData() == "trajectory")
        self.canvas.draw()
