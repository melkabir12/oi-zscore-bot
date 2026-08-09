"""
Petit wrapper HTTP commun à tous les adaptateurs d'exchange :
- essaie plusieurs hosts de fallback dans l'ordre
- retry avec backoff léger sur chaque host
- lève une exception explicite si TOUT échoue (jamais de valeur silencieuse)
"""
import logging
import time

import requests

import config

log = logging.getLogger("http_client")


class ExchangeFetchError(Exception):
    """Levée quand un exchange ne peut pas être interrogé avec succès."""


def get_json(hosts, path, params=None):
    """
    Essaie `path` (avec `params`) sur chaque host de `hosts`, dans l'ordre,
    avec HTTP_RETRIES tentatives par host. Retourne le JSON décodé du
    premier succès. Lève ExchangeFetchError si tout échoue.
    """
    last_error = None
    for host in hosts:
        url = f"{host}{path}"
        for attempt in range(1, config.HTTP_RETRIES + 1):
            try:
                r = requests.get(
                    url,
                    params=params,
                    headers=config.REST_HEADERS,
                    timeout=config.HTTP_TIMEOUT_SEC,
                )
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_error = e
                log.warning(
                    "Échec %s (tentative %d/%d) sur %s: %s",
                    path, attempt, config.HTTP_RETRIES, host, e,
                )
                if attempt < config.HTTP_RETRIES:
                    time.sleep(1.0 * attempt)
    raise ExchangeFetchError(f"Tous les hosts ont échoué pour {path}: {last_error}")
