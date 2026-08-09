"""
Calcul des Z-scores glissants (prix et volume) par exchange/paire.

Méthodologie (identique au rapport PDF de référence) :
- Pour chaque nouvelle bougie 1 min close, on calcule son Z-score par
  rapport à la moyenne et à l'écart-type des N bougies PRÉCÉDENTES
  (fenêtre glissante, N = ZSCORE_WINDOW). La bougie courante n'est PAS
  incluse dans le calcul de sa propre baseline — sinon un point extrême
  se "dilue" lui-même dans sa moyenne, ce qui sous-estime le Z-score.
- Après calcul, la bougie est ajoutée à l'historique pour servir de
  baseline aux bougies suivantes.

Écart-type : on utilise l'écart-type ÉCHANTILLON (ddof=1, comme
`statistics.stdev`), cohérent avec l'approche "estimation à partir d'un
échantillon" plutôt que "population complète connue".
"""
import statistics
from collections import deque

import config


def _safe_zscore(value: float, history) -> float:
    """
    Z-score de `value` par rapport à la moyenne/écart-type de `history`.
    Renvoie 0.0 si l'historique est trop court ou si l'écart-type est nul
    (évite toute division par zéro ou NaN qui polluerait une alerte).
    """
    if len(history) < 2:
        return 0.0
    mean = statistics.fmean(history)
    stdev = statistics.stdev(history)  # ddof=1
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev


class SymbolExchangeStats:
    """
    Historique + Z-scores courants pour UNE paire sur UN exchange.
    Alimenté bougie par bougie via `update()`.
    """

    def __init__(self, window: int = config.ZSCORE_WINDOW):
        self.window = window
        self.close_history = deque(maxlen=window)   # closes bruts (pour calcul du rendement)
        self.return_history = deque(maxlen=window)   # rendements % (baseline Z-prix)
        self.volume_history = deque(maxlen=window)    # volumes bruts (baseline Z-volume)

        self.last_ts = None
        self.last_close = None
        self.last_volume = None
        self.last_z_price = 0.0
        self.last_z_volume = 0.0
        self.last_z_combined = 0.0
        self.ready = False  # True une fois assez d'historique accumulé

    def update(self, ts: int, close: float, volume: float) -> dict:
        """
        Intègre une nouvelle bougie CLOSE. Renvoie un dict avec les
        Z-scores calculés pour CETTE bougie (basés sur l'historique
        précédent, donc pas de fuite de données de la bougie elle-même).
        """
        return_pct = None
        if self.close_history:
            prev_close = self.close_history[-1]
            if prev_close > 0:
                return_pct = (close - prev_close) / prev_close * 100.0

        z_price = 0.0
        if return_pct is not None:
            z_price = _safe_zscore(return_pct, self.return_history)

        z_volume = _safe_zscore(volume, self.volume_history)

        # Score combiné : |Z_prix| (un choc de prix compte dans les 2 sens)
        # + max(Z_volume, 0) (seul un EXCÈS de volume doit compter, une
        # baisse de volume ne doit pas gonfler artificiellement le score).
        z_combined = config.W_PRICE * abs(z_price) + config.W_VOLUME * max(z_volume, 0.0)

        # Mise à jour de l'historique pour les prochaines bougies
        self.close_history.append(close)
        if return_pct is not None:
            self.return_history.append(return_pct)
        self.volume_history.append(volume)

        self.last_ts = ts
        self.last_close = close
        self.last_volume = volume
        self.last_z_price = z_price
        self.last_z_volume = z_volume
        self.last_z_combined = z_combined
        self.ready = len(self.return_history) >= config.MIN_HISTORY_FOR_ZSCORE

        return {
            "ts": ts,
            "close": close,
            "volume": volume,
            "return_pct": return_pct,
            "z_price": z_price,
            "z_volume": z_volume,
            "z_combined": z_combined,
            "ready": self.ready,
        }

    def to_state(self) -> dict:
        """Sérialisation pour persistance disque."""
        return {
            "close_history": list(self.close_history),
            "return_history": list(self.return_history),
            "volume_history": list(self.volume_history),
            "last_ts": self.last_ts,
        }

    def load_state(self, state: dict):
        if not state:
            return
        self.close_history = deque(state.get("close_history", []), maxlen=self.window)
        self.return_history = deque(state.get("return_history", []), maxlen=self.window)
        self.volume_history = deque(state.get("volume_history", []), maxlen=self.window)
        self.last_ts = state.get("last_ts")
        self.ready = len(self.return_history) >= config.MIN_HISTORY_FOR_ZSCORE
