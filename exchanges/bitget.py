"""
Adaptateur Bitget v2 (productType usdt-futures = perpetuals USDT-M).
Doc officielle : https://www.bitget.com/api-doc/contract/market/Get-Candle-Data
                 https://www.bitget.com/api-doc/contract/market/Get-Open-Interest

ATTENTION (transparence) : le schéma exact de la réponse "open-interest" de
Bitget est moins standardisé dans la doc publique que les 3 autres exchanges.
Ce module gère plusieurs formes de réponse possibles et lève une erreur
explicite si aucune ne correspond, plutôt que de renvoyer une valeur fausse
silencieusement. -> Lance test_exchanges.py AVANT le déploiement 24/7 pour
confirmer que ça matche bien la réponse réelle actuelle de l'API.

Interface standardisée :
    fetch_kline(symbol) -> {"ts": int_ms, "close": float, "volume": float}
    fetch_oi(symbol)    -> {"ts": int_ms, "oi_qty": float}
"""
import config
from http_client import get_json

NAME = "bitget"
HOSTS = config.REST_HOSTS["bitget"]


def fetch_kline(symbol: str) -> dict:
    data = get_json(HOSTS, "/api/v2/mix/market/candles", {
        "symbol": symbol, "productType": "usdt-futures",
        "granularity": "1m", "limit": 3,
    })
    if str(data.get("code")) != "00000":
        raise ValueError(f"[bitget] Erreur API klines pour {symbol}: {data}")

    rows = data["data"]
    if len(rows) < 2:
        raise ValueError(f"[bitget] Pas assez de bougies pour {symbol}: {rows}")

    # On ne suppose pas l'ordre (asc/desc) renvoyé par l'API : on trie nous-
    # mêmes par timestamp croissant, puis on prend l'avant-dernière ligne
    # (la dernière pouvant être la bougie en cours de formation).
    rows_sorted = sorted(rows, key=lambda r: int(r[0]))
    row = rows_sorted[-2]  # [ts, open, high, low, close, baseVol, quoteVol]
    return {
        "ts": int(row[0]),
        "close": float(row[4]),
        "volume": float(row[5]),
    }


def fetch_oi(symbol: str) -> dict:
    data = get_json(HOSTS, "/api/v2/mix/market/open-interest", {
        "symbol": symbol, "productType": "usdt-futures",
    })
    if str(data.get("code")) != "00000":
        raise ValueError(f"[bitget] Erreur API OI pour {symbol}: {data}")

    payload = data["data"]

    # Forme 1 (la plus courante d'après la doc) : objet unique avec une clé
    # "openInterestList" contenant [{"symbol":..., "size": "..."}]
    if isinstance(payload, dict) and "openInterestList" in payload:
        items = payload["openInterestList"]
        if not items:
            raise ValueError(f"[bitget] openInterestList vide pour {symbol}: {data}")
        item = items[0]
        qty = item.get("size") or item.get("amount")
        if qty is None:
            raise ValueError(f"[bitget] Champ quantité OI introuvable pour {symbol}: {item}")
        return {"ts": int(payload.get("ts", 0)), "oi_qty": float(qty)}

    # Forme 2 : objet plat {"symbol":..., "amount": "...", "ts": "..."}
    if isinstance(payload, dict) and ("amount" in payload or "size" in payload):
        qty = payload.get("amount") or payload.get("size")
        return {"ts": int(payload.get("ts", 0)), "oi_qty": float(qty)}

    raise ValueError(
        f"[bitget] Schéma de réponse OI non reconnu pour {symbol}, "
        f"à vérifier/adapter via test_exchanges.py: {data}"
    )
