"""
Sauvegarde/chargement de l'état complet du bot (historiques Z-score par
exchange/paire + dernières valeurs d'OI connues) pour survivre à un
redémarrage ou un redeploy Railway.

IMPORTANT : le filesystem Railway est éphémère par défaut. Pour que ce
fichier survive à un redeploy, monter un Volume Railway et pointer
STATE_FILE dessus (ex: STATE_FILE=/data/state.json avec Volume sur /data).
"""
import json
import logging
import os

import config

log = logging.getLogger("state")


def save_state(payload: dict):
    """Sauvegarde générique d'un blob JSON, écriture atomique (tmp + replace)."""
    try:
        tmp_path = config.STATE_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(payload, f)
        os.replace(tmp_path, config.STATE_FILE)
    except Exception as e:
        log.warning("Échec sauvegarde état (%s): %s", config.STATE_FILE, e)


def load_state() -> dict:
    default = {"zscore": {}, "oi": {}, "oi_aggregate": {}}
    if not os.path.exists(config.STATE_FILE):
        log.info("Aucun état sauvegardé trouvé (%s) — démarrage à froid", config.STATE_FILE)
        return default
    try:
        with open(config.STATE_FILE, "r") as f:
            data = json.load(f)
        log.info(
            "État précédent chargé (%d séries Z-score, %d entrées OI)",
            len(data.get("zscore", {})), len(data.get("oi", {})),
        )
        for key in default:
            data.setdefault(key, {})
        return data
    except Exception as e:
        log.warning("Échec lecture état (%s): %s — démarrage à froid", config.STATE_FILE, e)
        return default
