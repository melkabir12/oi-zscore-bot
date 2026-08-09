"""
Tests unitaires purement locaux (aucun accès réseau requis) qui vérifient
que le calcul du Z-score est mathématiquement correct, en le comparant à
un calcul de référence indépendant fait "à la main" avec statistics.

Lancer avec : python3 test_math.py
"""
import statistics
from collections import deque

from zscore import SymbolExchangeStats, _safe_zscore
import config


def test_zscore_matches_manual_reference():
    """
    On rejoue 25 bougies avec des prix/volumes connus, et on vérifie que
    le Z-score renvoyé par SymbolExchangeStats correspond exactement à un
    calcul manuel (moyenne/écart-type de la fenêtre PRÉCÉDENTE).
    """
    stats = SymbolExchangeStats(window=20)

    prices = [100.0, 100.5, 99.8, 100.2, 100.1, 99.9, 100.3, 100.0, 100.4,
              99.7, 100.6, 100.2, 99.9, 100.1, 100.0, 100.3, 99.8, 100.5,
              100.2, 99.9, 100.1, 105.0]  # dernière bougie = choc de prix volontaire
    volumes = [10, 12, 9, 11, 10, 13, 8, 12, 11, 9, 10, 14, 9, 11, 10, 12,
               9, 11, 10, 13, 12, 80]  # dernier volume = pic volontaire

    assert len(prices) == len(volumes)

    manual_returns = deque(maxlen=20)
    manual_volumes = deque(maxlen=20)
    prev_price = None
    results = []

    for i, (price, vol) in enumerate(zip(prices, volumes)):
        # -- calcul de référence "à la main", AVANT d'appeler update() --
        ref_return = None
        if prev_price is not None:
            ref_return = (price - prev_price) / prev_price * 100.0

        ref_z_price = _reference_zscore(ref_return, manual_returns)
        ref_z_volume = _reference_zscore(vol, manual_volumes)

        # -- calcul via le module testé --
        res = stats.update(ts=i, close=price, volume=vol)

        assert _almost_equal(res["z_price"], ref_z_price), (
            f"Étape {i}: z_price attendu={ref_z_price}, obtenu={res['z_price']}"
        )
        assert _almost_equal(res["z_volume"], ref_z_volume), (
            f"Étape {i}: z_volume attendu={ref_z_volume}, obtenu={res['z_volume']}"
        )

        expected_combined = config.W_PRICE * abs(ref_z_price) + config.W_VOLUME * max(ref_z_volume, 0.0)
        assert _almost_equal(res["z_combined"], expected_combined), (
            f"Étape {i}: z_combined attendu={expected_combined}, obtenu={res['z_combined']}"
        )

        # -- mise à jour de l'historique de référence pour l'étape suivante --
        if ref_return is not None:
            manual_returns.append(ref_return)
        manual_volumes.append(vol)
        prev_price = price
        results.append(res)

    # Vérification "de bon sens" : la dernière bougie (choc de prix +
    # pic de volume délibéré) doit produire un Z-score nettement positif.
    last = results[-1]
    assert last["z_price"] > 3, f"Le choc de prix simulé devrait donner un Z-price élevé, obtenu={last['z_price']}"
    assert last["z_volume"] > 3, f"Le pic de volume simulé devrait donner un Z-volume élevé, obtenu={last['z_volume']}"
    print(f"OK — dernière bougie: z_price={last['z_price']:.2f}, "
          f"z_volume={last['z_volume']:.2f}, z_combined={last['z_combined']:.2f}")


def test_zscore_no_division_by_zero():
    """Un historique constant (écart-type nul) ne doit jamais lever d'exception ni renvoyer NaN."""
    stats = SymbolExchangeStats(window=20)
    for i in range(15):
        res = stats.update(ts=i, close=100.0, volume=10.0)  # toujours la même valeur
        assert res["z_price"] == 0.0
        assert res["z_volume"] == 0.0
    print("OK — pas de division par zéro sur historique constant")


def test_zscore_short_history_returns_zero():
    """Avec moins de 2 points d'historique, le Z-score doit être 0.0 (pas d'erreur)."""
    stats = SymbolExchangeStats(window=20)
    res = stats.update(ts=0, close=100.0, volume=10.0)
    assert res["z_price"] == 0.0  # pas de return_pct possible sur la 1ère bougie
    assert res["z_volume"] == 0.0  # historique vide
    print("OK — historique court géré sans erreur")


def _reference_zscore(value, history):
    if value is None or len(history) < 2:
        return 0.0
    mean = statistics.fmean(history)
    stdev = statistics.stdev(history)
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev


def _almost_equal(a, b, tol=1e-9):
    return abs(a - b) < tol


if __name__ == "__main__":
    test_zscore_no_division_by_zero()
    test_zscore_short_history_returns_zero()
    test_zscore_matches_manual_reference()
    print("\nTous les tests mathématiques sont passés avec succès.")
