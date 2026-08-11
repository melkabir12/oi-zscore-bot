import logging
import os
import requests

log = logging.getLogger("redis_gate")

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
HEADERS = {"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"}

FLAG_PREFIX = "trigger_active"


def is_trigger_active(coin: str) -> bool:
    """
    Appelé par le bot SECONDAIRE (z-score) avant chaque cycle d'analyse,
    pour un coin donné (BTC, ETH ou XRP).
    """
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        log.warning("Upstash non configuré (URL/token manquant) — trigger considéré inactif")
        return False

    key = f"{FLAG_PREFIX}:{coin}"
    try:
        r = requests.get(
            f"{UPSTASH_REDIS_REST_URL}/get/{key}",
            headers=HEADERS,
            timeout=5,
        )
        data = r.json()
        return data.get("result") == "1"
    except Exception as e:
        log.warning("Erreur is_trigger_active(%s): %s", coin, e)
        return False
