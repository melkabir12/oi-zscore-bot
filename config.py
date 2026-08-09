"""
Configuration centrale du bot Z-score + Open Interest multi-exchange.

Tous les seuils/paramètres sont modifiables via variables d'environnement
(pratique pour ajuster depuis Railway sans toucher au code).
"""
import os

# ── Paires suivies ────────────────────────────────────────────────
# Nom générique interne -> mapping vers le symbole exact de chaque exchange
# (voir plus bas EXCHANGE_SYMBOL_MAP). C'est volontairement découplé car
# chaque exchange a sa propre convention de nommage.
SYMBOLS = ["BTC", "ETH", "XRP"]

EXCHANGE_SYMBOL_MAP = {
    "binance": {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "XRP": "XRPUSDT"},
    "bybit":   {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "XRP": "XRPUSDT"},
    "okx":     {"BTC": "BTC-USDT-SWAP", "ETH": "ETH-USDT-SWAP", "XRP": "XRP-USDT-SWAP"},
    "bitget":  {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "XRP": "XRPUSDT"},
}

EXCHANGES = ["binance", "bybit", "okx", "bitget"]

# ── Fenêtre statistique (Z-score) ──────────────────────────────────
# Nombre de bougies 1 min utilisées comme baseline glissante pour
# calculer moyenne/écart-type (même logique que le rapport PDF : 20 min).
ZSCORE_WINDOW = int(os.environ.get("ZSCORE_WINDOW", "20"))

# Nombre minimum de bougies accumulées avant d'autoriser un calcul de Z-score
# fiable pour un exchange donné (évite les faux signaux au démarrage).
MIN_HISTORY_FOR_ZSCORE = int(os.environ.get("MIN_HISTORY_FOR_ZSCORE", "10"))

# ── Pondération du score combiné par exchange ──────────────────────
# score_combiné = W_PRICE * |Z_prix| + W_VOLUME * max(Z_volume, 0)
# (Z_volume est plafonné à 0 côté négatif : une baisse de volume ne doit
#  pas "aider" à déclencher une alerte de pic.)
W_PRICE = float(os.environ.get("W_PRICE", "0.6"))
W_VOLUME = float(os.environ.get("W_VOLUME", "0.4"))

# ── Seuil de déclenchement ──────────────────────────────────────────
# Alerte si la MOYENNE des scores combinés des exchanges ayant répondu
# avec succès sur ce cycle est >= ALERT_THRESHOLD.
ALERT_THRESHOLD = float(os.environ.get("ALERT_THRESHOLD", "3.0"))

# Nombre minimum d'exchanges devant avoir répondu sur le cycle pour que
# la moyenne soit considérée valide (si moins, on ignore le cycle pour
# cette paire plutôt que de calculer une moyenne non représentative).
MIN_EXCHANGES_FOR_ALERT = int(os.environ.get("MIN_EXCHANGES_FOR_ALERT", "2"))

# ── Open Interest ────────────────────────────────────────────────
# Fréquence de polling de l'OI (secondes). 5 min = 300s, comme convenu.
OI_POLL_INTERVAL_SEC = int(os.environ.get("OI_POLL_INTERVAL_SEC", "300"))

# ── Boucle prix/volume ──────────────────────────────────────────────
# Fréquence de polling des klines 1 min (secondes). On interroge un peu
# après le début de chaque minute pour laisser le temps à la bougie
# précédente d'être bien clôturée côté exchange.
KLINE_POLL_INTERVAL_SEC = int(os.environ.get("KLINE_POLL_INTERVAL_SEC", "60"))
KLINE_POLL_OFFSET_SEC = int(os.environ.get("KLINE_POLL_OFFSET_SEC", "5"))

# ── Telegram ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Persistance d'état (survit aux redeploys si un Volume Railway
# est monté sur le dossier contenant ce fichier, ex: /data) ──────────
STATE_FILE = os.environ.get("STATE_FILE", "zscore_oi_state.json")

# ── Réseau ───────────────────────────────────────────────────────
HTTP_TIMEOUT_SEC = int(os.environ.get("HTTP_TIMEOUT_SEC", "10"))
HTTP_RETRIES = int(os.environ.get("HTTP_RETRIES", "2"))

REST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Hosts REST par exchange, avec fallback (le premier qui répond est utilisé).
REST_HOSTS = {
    "binance": ["https://fapi.binance.com"],
    "bybit": ["https://api.bybit.com", "https://api.bytick.com"],
    "okx": ["https://www.okx.com"],
    "bitget": ["https://api.bitget.com"],
}
