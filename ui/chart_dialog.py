from PySide6.QtWidgets import QDialog, QVBoxLayout


class ChartDialog(QDialog):
    def __init__(self, result, parent):
        super().__init__(parent)
        from visualizations.charts import make_figure
        figure = make_figure(result)
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
        self.setWindowTitle("Grafico · zoom, pan ed esportazione")
        self.resize(1100, 700)
        layout = QVBoxLayout(self)
        canvas = FigureCanvasQTAgg(figure)
        layout.addWidget(NavigationToolbar2QT(canvas, self))
        layout.addWidget(canvas)
        canvas.draw()
