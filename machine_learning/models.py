import numpy as np

MODELS = ("uniform", "frequency", "temporal", "logistic", "random_forest", "gradient_boosting", "xgboost", "ensemble")


def features(history: np.ndarray) -> np.ndarray:
    if not len(history):
        raise ValueError("Storico vuoto")
    return np.concatenate([history[-1].astype(float)] +
                          [history[-window:].mean(axis=0) for window in (10, 25, 50)])


class ExperimentalModel:
    def __init__(self, name: str, count: int, seed: int = 42):
        if name not in MODELS:
            raise ValueError("Modello non supportato")
        self.name, self.count, self.seed = name, count, seed
        self.estimators = None
        self.version_cutoff = None
        self.members = {}
        self.weights = {}

    def fit(self, history: np.ndarray):
        if history.ndim != 2 or not len(history):
            raise ValueError("Storico non valido")
        self.version_cutoff = len(history)
        if self.name == "ensemble":
            return self.fit_ensemble(history)
        if self.name in ("uniform", "frequency", "temporal"):
            return self
        if len(history) < 40:
            raise ValueError("I modelli ML richiedono almeno 40 estrazioni precedenti")
        from sklearn.dummy import DummyClassifier
        from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
        from sklearn.linear_model import LogisticRegression
        # Target t: feature da [0,t), senza includere la riga target.
        x = np.asarray([features(history[:t]) for t in range(25, len(history))])
        y = history[25:]
        self.estimators = []
        for column in range(history.shape[1]):
            labels = y[:, column]
            if len(np.unique(labels)) == 1:
                estimator = DummyClassifier(strategy="constant", constant=int(labels[0]))
            elif self.name == "logistic":
                estimator = LogisticRegression(C=.1, max_iter=500, random_state=self.seed)
            elif self.name == "random_forest":
                estimator = RandomForestClassifier(n_estimators=40, max_depth=4, min_samples_leaf=5,
                                                    random_state=self.seed, n_jobs=1)
            elif self.name == "gradient_boosting":
                estimator = HistGradientBoostingClassifier(max_iter=40, max_leaf_nodes=7,
                                                           l2_regularization=1, random_state=self.seed)
            else:
                try:
                    from xgboost import XGBClassifier
                except ImportError as error:
                    raise ValueError("XGBoost opzionale non installato") from error
                estimator = XGBClassifier(n_estimators=40, max_depth=3, learning_rate=.05,
                                          random_state=self.seed, n_jobs=1, eval_metric="logloss")
            estimator.fit(x, labels)
            self.estimators.append(estimator)
        return self

    def fit_ensemble(self, history):
        if len(history) < 100:
            raise ValueError("Ensemble: servono almeno 100 estrazioni per training e validazione interna")
        from backtesting.engine import null_tail
        from lotto_statistics.engine import holm
        initial = min(len(history) - 30, max(40, int(len(history) * .7)))
        candidates = {name: ExperimentalModel(name, self.count, self.seed)
                      for name in ("frequency", "temporal", "logistic")}
        expected = self.count ** 2 / history.shape[1]
        means, ps = [], []
        for name, candidate in candidates.items():
            rng = np.random.default_rng(self.seed)
            matches = []
            for t in range(initial, len(history)):
                if (t - initial) % 10 == 0:
                    candidate.fit(history[:t])
                ticket = top_ticket(candidate.score(history[:t]), self.count, rng)
                matches.append(int(history[t, ticket].sum()))
            means.append(float(np.mean(matches)))
            ps.append(null_tail(sum(matches), len(matches), history.shape[1], self.count))
        adjusted = holm(ps)
        improvements = {name: max(0.0, mean - expected) if pv < .05 else 0.0
                        for name, mean, pv in zip(candidates, means, adjusted)}
        total = sum(improvements.values())
        self.weights = {name: improvement / total for name, improvement in improvements.items()
                        if improvement > 0} if total else {}
        self.members = {name: candidates[name].fit(history) for name in self.weights}
        self.validation = {"steps": len(history) - initial, "weights": self.weights,
                           "candidate_names": list(candidates), "mean_matches": means, "p_holm": adjusted,
                           "fallback_uniform": not bool(self.weights)}
        return self

    def score(self, history: np.ndarray) -> np.ndarray:
        if self.version_cutoff is None:
            raise ValueError("Addestrare il modello prima di generare punteggi")
        p = self.count / history.shape[1]
        if self.name == "ensemble":
            if not self.weights:
                return np.full(history.shape[1], p)
            return sum(self.weights[name] * member.score(history) for name, member in self.members.items())
        if self.name == "uniform":
            return np.full(history.shape[1], p)
        if self.name == "frequency":
            return (history.sum(axis=0) + 20 * p) / (len(history) + 20)
        if self.name == "temporal":
            recent = history[-50:]
            return (recent.sum(axis=0) + 20 * p) / (len(recent) + 20)
        x = features(history).reshape(1, -1)
        result = []
        for estimator in self.estimators:
            classes = list(estimator.classes_)
            result.append(float(estimator.predict_proba(x)[0, classes.index(1)]) if 1 in classes else 0.0)
        return np.asarray(result)


def top_ticket(scores: np.ndarray, count: int, rng: np.random.Generator) -> np.ndarray:
    """Risoluzione casuale riproducibile degli ex aequo, senza preferenza numerica."""
    if scores.ndim != 1 or len(scores) < count or not np.isfinite(scores).all():
        raise ValueError("Punteggi non validi")
    return np.lexsort((rng.random(len(scores)), -scores))[:count]
