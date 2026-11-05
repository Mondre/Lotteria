import os
from pathlib import Path

from config.settings import data_directory


def make_figure(result: dict, view: str = "frequencies", number: int | None = None):
    cache = data_directory() / "matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    xdg_cache = cache / "xdg"
    xdg_cache.mkdir(exist_ok=True)
    os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache))
    from matplotlib.figure import Figure
    figure = Figure(figsize=(11, 6), facecolor="#101827")
    axes = figure.add_subplot(111)
    axes.set_facecolor("#172339")
    axes.tick_params(colors="#e5edf9")
    axes.xaxis.label.set_color("#e5edf9")
    axes.yaxis.label.set_color("#e5edf9")
    axes.title.set_color("#e5edf9")
    if "summary" in result and "steps" in result:
        import numpy as np
        for model in result["summary"]:
            name = model["model"]
            scores = np.asarray([step["models"][name]["matches"] for step in result["steps"]])
            axes.plot(np.arange(1, len(scores) + 1), np.cumsum(scores) / np.arange(1, len(scores) + 1), label=name)
        axes.axhline(result["summary"][0]["theoretical_random_mean"], color="#f7b955", linestyle="--", label="Attesa teorica casuale")
        axes.set(xlabel="Estrazioni di test (ordine cronologico)", ylabel="Corrispondenze medie cumulative",
                 title="Backtest sintetico" if result["synthetic"] else "Backtest su dati importati")
    elif "samples" in result:
        # Numerazione coerente anche per intervalli configurabili con minimo diverso da uno.
        start = result.get("minimum", 1)
        axes.bar(range(start, start + len(result["frequencies"])), result["frequencies"], color="#458df0", label="Frequenza simulata")
        axes.axhline(result["expected_frequency"], color="#f7b955", linestyle="--", label="Attesa teorica")
        axes.set(xlabel="Numero", ylabel="Presenze", title=f"Monte Carlo · {result['samples']:,} estrazioni sintetiche")
    elif "frequencies" in result and view == "delays":
        rows = result["delays"]
        axes.bar([row["number"] for row in rows], [row["current"] for row in rows], color="#458df0", label="Ritardo attuale")
        axes.set(xlabel="Numero", ylabel="Estrazioni senza uscita", title="Ritardi osservati · non aumentano la probabilità futura")
    elif "frequencies" in result and view == "sums":
        values = [row["sum"] for row in result["structures"]]
        axes.hist(values, bins=min(20, max(values) - min(values) + 1), color="#458df0", label="Distribuzione osservata")
        axes.set(xlabel="Somma dei numeri principali", ylabel="Estrazioni", title="Somme · finestra analizzata")
    elif "frequencies" in result and view == "trajectory":
        row = next((row for row in result["frequencies"] if row["number"] == number), None)
        if not row or not row.get("trajectory"):
            raise ValueError("Andamento non disponibile per questo numero")
        axes.plot([point["draws"] for point in row["trajectory"]], [point["relative"] for point in row["trajectory"]], color="#458df0", label=f"Numero {number}")
        axes.axhline(row["expected_count"] / result["draws"], color="#f7b955", linestyle="--", label="Riferimento teorico")
        axes.set(xlabel="Estrazioni dall'inizio della serie", ylabel="Frequenza cumulativa", title="Andamento descrittivo · non previsione")
    elif "frequencies" in result:
        rows = result["frequencies"]
        axes.bar([row["number"] for row in rows], [row["relative"] for row in rows], color="#458df0", label="Frequenza relativa")
        expected = rows[0]["expected_count"] / result["draws"]
        axes.axhline(expected, color="#f7b955", linestyle="--", label="Attesa teorica")
        axes.set(xlabel="Numero", ylabel="Quota di estrazioni", title="Frequenze · dati sintetici" if result["synthetic"] else "Frequenze · dati importati")
    else:
        raise ValueError("Questo risultato non contiene una serie da rappresentare")
    axes.legend(facecolor="#243756", labelcolor="#e5edf9")
    figure.tight_layout()
    return figure


def export_png(result: dict, path: Path) -> None:
    figure = make_figure(result)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    FigureCanvasAgg(figure).print_png(str(path))
