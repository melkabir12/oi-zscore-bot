"""
Adaptateur Bybit v5 (catégorie "linear" = USDT perpetuals).
Doc officielle : https://bybit-exchange.github.io/docs/v5/market/kline
                 https://bybit-exchange.github.io/docs/v5/market/open-interest

Interface standardisée :
    fetch_kline(symbol) -> {"ts": int_ms, "close": float, "volume": float}
    fetch_oi(symbol)    -> {"ts": int_ms, "oi_qty": float}
"""
import config
from http_client import get_json

NAME = "bybit"
HOSTS = config.REST_HOSTS["bybit"]  # inclut le fallback api.bytick.com


def fetch_kline(symbol: str) -> dict:
    data = get_json(HOSTS, "/v5/market/kline", {
        "category": "linear", "symbol": symbol, "interval": "1", "limit": 3,
    })
    if data.get("retCode") != 0:
        raise ValueError(f"[bybit] Erreur API klines pour {symbol}: {data}")

    rows = data["result"]["list"]  # ordre : le plus récent en premier
    if len(rows) < 2:
        raise ValueError(f"[bybit] Pas assez de bougies pour {symbol}: {rows}")

    # rows[0] = bougie en cours (potentiellement non close) -> on prend rows[1]
    row = rows[1]  # [start, open, high, low, close, volume, turnover]
    return {
        "ts": int(row[0]),
        "close": float(row[4]),
        "volume": float(row[5]),
    }


def fetch_oi(symbol: str) -> dict:
    data = get_json(HOSTS, "/v5/market/open-interest", {
        "category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": 1,
    })
    if data.get("retCode") != 0:
        raise ValueError(f"[bybit] Erreur API OI pour {symbol}: {data}")

    rows = data["result"]["list"]
    if not rows:
        raise ValueError(f"[bybit] Réponse OI vide pour {symbol}: {data}")

    row = rows[0]  # {"openInterest": "...", "timestamp": "..."}
    return {
        "ts": int(row["timestamp"]),
        "oi_qty": float(row["openInterest"]),
    }
