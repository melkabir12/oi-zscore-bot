"""
Adaptateur OKX v5 (instType SWAP = perpetuals).
Doc officielle : https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks
                 https://www.okx.com/docs-v5/en/#public-data-rest-api-get-open-interest

Interface standardisée :
    fetch_kline(symbol) -> {"ts": int_ms, "close": float, "volume": float}
    fetch_oi(symbol)    -> {"ts": int_ms, "oi_qty": float}

Note : pour rester cohérent avec les autres exchanges (volume exprimé en
coin, ex. BTC, et pas en nombre de contrats), on utilise volCcy pour les
klines et oiCcy pour l'OI (champs OKX exprimés en devise sous-jacente).
"""
import config
from http_client import get_json

NAME = "okx"
HOSTS = config.REST_HOSTS["okx"]


def fetch_kline(symbol: str) -> dict:
    data = get_json(HOSTS, "/api/v5/market/candles", {
        "instId": symbol, "bar": "1m", "limit": 3,
    })
    if data.get("code") != "0":
        raise ValueError(f"[okx] Erreur API klines pour {symbol}: {data}")

    rows = data["data"]  # ordre : le plus récent en premier
    # row = [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
    # confirm == "1" -> bougie close ; "0" -> bougie en cours de formation
    closed_rows = [r for r in rows if len(r) > 8 and r[8] == "1"]
    if not closed_rows:
        raise ValueError(f"[okx] Aucune bougie close trouvée pour {symbol}: {rows}")

    row = closed_rows[0]
    return {
        "ts": int(row[0]),
        "close": float(row[4]),
        "volume": float(row[6]),  # volCcy = volume en coin sous-jacent
    }


def fetch_oi(symbol: str) -> dict:
    data = get_json(HOSTS, "/api/v5/public/open-interest", {"instId": symbol})
    if data.get("code") != "0":
        raise ValueError(f"[okx] Erreur API OI pour {symbol}: {data}")

    rows = data["data"]
    if not rows:
        raise ValueError(f"[okx] Réponse OI vide pour {symbol}: {data}")

    row = rows[0]  # {"instId":..., "oi": "contrats", "oiCcy": "coin", "ts": "..."}
    return {
        "ts": int(row["ts"]),
        "oi_qty": float(row["oiCcy"]),
    }
