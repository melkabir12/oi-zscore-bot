"""
Petit wrapper HTTP commun à tous les adaptateurs d'exchange :
- essaie plusieurs hosts de fallback dans l'ordre
- retry avec backoff léger sur chaque host
- route automatiquement certains exchanges (Binance, Bybit) via un proxy
  si une URL de proxy est configurée pour eux (voir config.PROXY_URLS),
  pour contourner les blocages géographiques (451) / Cloudflare (403)
- lève une exception explicite si TOUT échoue (jamais de valeur silencieuse)
"""
import logging
import time

import requests

import config

log = logging.getLogger("http_client")


class ExchangeFetchError(Exception):
    """Levée quand un exchange ne peut pas être interrogé avec succès."""


def _proxy_for_host(host: str):
    """
    Détermine si `host` doit passer par un proxy, en se basant sur
    config.PROXY_URLS. Renvoie un dict `proxies` prêt pour `requests`
    (ou None si pas de proxy applicable / configuré pour cet exchange).
    """
    for exchange_key, proxy_url in config.PROXY_URLS.items():
        if not proxy_url:
            continue
        # binance -> "fapi.binance.com" ; bybit -> "api.bybit.com" / "api.bytick.com"
        if exchange_key in host or (exchange_key == "bybit" and "bytick" in host):
            return {"http": proxy_url, "https": proxy_url}
    return None


def get_json(hosts, path, params=None):
    """
    Essaie `path` (avec `params`) sur chaque host de `hosts`, dans l'ordre,
    avec HTTP_RETRIES tentatives par host. Retourne le JSON décodé du
    premier succès. Lève ExchangeFetchError si tout échoue.
    """
    last_error = None
    for host in hosts:
        url = f"{host}{path}"
        proxies = _proxy_for_host(host)
        for attempt in range(1, config.HTTP_RETRIES + 1):
            try:
                r = requests.get(
                    url,
                    params=params,
                    headers=config.REST_HEADERS,
                    timeout=config.HTTP_TIMEOUT_SEC,
                    proxies=proxies,
                )
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_error = e
                via_proxy = " via proxy" if proxies else ""
                log.warning(
                    "Échec %s (tentative %d/%d) sur %s%s: %s",
                    path, attempt, config.HTTP_RETRIES, host, via_proxy, e,
                )
                if attempt < config.HTTP_RETRIES:
                    time.sleep(1.0 * attempt)
    raise ExchangeFetchError(f"Tous les hosts ont échoué pour {path}: {last_error}")
