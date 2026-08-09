"""
Adaptateur Binance Futures (USDT-M perpetuals).
Doc officielle : https://binance-docs.github.io/apidocs/futures/en/

Interface standardisée exposée à main.py :
    fetch_kline(symbol) -> {"ts": int_ms, "close": float, "volume": float}
    fetch_oi(symbol)    -> {"ts": int_ms, "oi_qty": float}   (OI en coin, ex: BTC)
"""
import config
from http_client import get_json

NAME = "binance"
HOSTS = config.REST_HOSTS["binance"]


def fetch_kline(symbol: str) -> dict:
    # limit=3 : on demande 3 bougies pour être certain d'avoir au moins
    # une bougie CLOSE. La dernière renvoyée par Binance est la bougie en
    # cours de formation (non close) -> on prend systématiquement l'avant-
    # dernière, qui est garantie close.
    data = get_json(HOSTS, "/fapi/v1/klines", {
        "symbol": symbol, "interval": "1m", "limit": 3,
    })
    if not isinstance(data, list) or len(data) < 2:
        raise ValueError(f"[binance] Réponse klines inattendue pour {symbol}: {data}")

    row = data[-2]  # [openTime, open, high, low, close, volume, closeTime, ...]
    return {
        "ts": int(row[0]),
        "close": float(row[4]),
        "volume": float(row[5]),
    }


def fetch_oi(symbol: str) -> dict:
    data = get_json(HOSTS, "/fapi/v1/openInterest", {"symbol": symbol})
    if "openInterest" not in data:
        raise ValueError(f"[binance] Réponse OI inattendue pour {symbol}: {data}")
    return {
        "ts": int(data.get("time", 0)),
        "oi_qty": float(data["openInterest"]),
    }
