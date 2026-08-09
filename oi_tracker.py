"""
Suivi de l'Open Interest par exchange + agrégation multi-exchange.

Méthode de calcul :
- Chaque exchange renvoie l'OI en quantité de coin (BTC, ETH, XRP).
- On le convertit en notionnel USD : oi_qty * dernier prix connu (close
  de la dernière bougie 1 min reçue pour cet exchange/paire), pour que
  l'agrégat multi-exchange soit comparable (les tailles de contrat et
  les modes de marge diffèrent selon les exchanges — additionner des
  quantités de contrats bruts n'aurait pas de sens).
- La variation affichée est calculée par rapport à la valeur du poll
  précédent (OI_LOOKBACK_POLLS cycles en arrière, 1 cycle = 5 min par
  défaut). Aucun seuil de classification n'est appliqué : le chiffre
  brut est toujours affiché tel quel, comme demandé.
"""
import logging
from collections import deque

import config

log = logging.getLogger("oi_tracker")

# Nombre de cycles de poll en arrière utilisés comme référence pour le
# calcul de la variation (1 = vs le poll précédent, soit ~5 min en arrière).
OI_LOOKBACK_POLLS = int(__import__("os").environ.get("OI_LOOKBACK_POLLS", "1"))


class OiSeries:
    """Historique de notionnel USD pour UN exchange/UNE paire."""

    def __init__(self, maxlen: int = 50):
        self.notional_history = deque(maxlen=maxlen)
        self.last_ts = None
        self.last_oi_qty = None
        self.last_notional_usd = None

    def update(self, ts: int, oi_qty: float, price: float) -> dict:
        notional_usd = oi_qty * price
        variation_pct = None
        if len(self.notional_history) >= OI_LOOKBACK_POLLS:
            ref = self.notional_history[-OI_LOOKBACK_POLLS]
            if ref > 0:
                variation_pct = (notional_usd - ref) / ref * 100.0

        self.notional_history.append(notional_usd)
        self.last_ts = ts
        self.last_oi_qty = oi_qty
        self.last_notional_usd = notional_usd

        return {
            "ts": ts,
            "oi_qty": oi_qty,
            "notional_usd": notional_usd,
            "variation_pct": variation_pct,
        }

    def to_state(self) -> dict:
        return {
            "notional_history": list(self.notional_history),
            "last_ts": self.last_ts,
        }

    def load_state(self, state: dict, maxlen: int = 50):
        if not state:
            return
        self.notional_history = deque(state.get("notional_history", []), maxlen=maxlen)
        self.last_ts = state.get("last_ts")


class AggregateOiSeries:
    """
    Historique de la SOMME des notionnels multi-exchange, avec son propre
    calcul de variation. On ne dérive PAS cette variation à partir des
    variations individuelles de chaque exchange (ça donnerait un résultat
    mathématiquement faux dès que le nombre d'exchanges ayant répondu
    change d'un cycle à l'autre) : on additionne d'abord les notionnels
    bruts, puis on calcule la variation sur cette somme, cycle par cycle.
    """

    def __init__(self, maxlen: int = 50):
        self.total_history = deque(maxlen=maxlen)

    def update(self, per_exchange_results: dict) -> dict:
        """
        per_exchange_results: {exchange: {"notional_usd": float, ...} or None}
        """
        current_total = 0.0
        n_ok = 0
        for ex, res in per_exchange_results.items():
            if res is not None and res.get("notional_usd") is not None:
                current_total += res["notional_usd"]
                n_ok += 1

        variation_pct = None
        if len(self.total_history) >= OI_LOOKBACK_POLLS:
            ref = self.total_history[-OI_LOOKBACK_POLLS]
            if ref > 0:
                variation_pct = (current_total - ref) / ref * 100.0

        self.total_history.append(current_total)

        return {
            "notional_usd": current_total,
            "n_exchanges": n_ok,
            "variation_pct": variation_pct,
        }

    def to_state(self) -> dict:
        return {"total_history": list(self.total_history)}

    def load_state(self, state: dict, maxlen: int = 50):
        if not state:
            return
        self.total_history = deque(state.get("total_history", []), maxlen=maxlen)
