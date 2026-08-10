"""
Vérifie l'état du flag partagé (Upstash Redis REST) qui indique si le bot
volume (primaire) a déclenché une alerte. Tant que ce flag n'est pas actif,
ce bot reste silencieux : pas d'appel exchange, pas de calcul Z-score.
"""
import logging
import os
import requests

log = logging.getLogger("redis_gate")

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

HEADERS = {"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"}
FLAG_KEY = "trigger_active"


def is_trigger_active() -> bool:
    """Appelé par le bot SECONDAIRE (z-score) avant chaque cycle d'analyse."""
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        log.warning("Upstash non configuré (URL/token manquant) — trigger considéré inactif")
        return False
    try:
        r = requests.get(
            f"{UPSTASH_REDIS_REST_URL}/get/{FLAG_KEY}",
            headers=HEADERS,
            timeout=5,
        )
        data = r.json()
        return data.get("result") == "1"
    except Exception as e:
        log.warning("Erreur is_trigger_active: %s", e)
        return False
