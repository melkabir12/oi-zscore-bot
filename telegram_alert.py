"""
Envoi de messages Telegram (alertes + notifications de statut).
"""
import logging
import math
import time
import requests
import config

log = logging.getLogger("telegram")


def zscore_to_score100(z: float) -> float:
    """
    Convertit un Z-score combiné BRUT (non borné, peut dépasser 100 sur un
    marché très calme suivi d'un pic brutal) en un score normalisé 0-100,
    dans le même esprit que la colonne "Score/100" du rapport PDF de
    référence — pour garder un affichage lisible même quand le Z brut
    explose (ex: 60, 130...).

    Transformation exponentielle saturante : score = 100 * (1 - e^(-z/K))
    - Monotone croissante, jamais négative, plafonnée à 100 sans jamais
      l'atteindre exactement (asymptote).
    - K=8 calibré pour que le seuil d'alerte (Z=3) tombe autour de ~30/100
      (signal "qui vient de déclencher"), et qu'un Z brut de 20+ soit déjà
      proche de 90+ (signal "extrême", cohérent avec les scores 82-100
      observés dans le rapport PDF pour les vraies anomalies).
    """
    z = max(z, 0.0)
    return 100.0 * (1.0 - math.exp(-z / 8.0))


def send_telegram(message: str, retries: int = 3):
    """
    Envoie un message Telegram avec retry automatique en cas d'échec réseau
    (timeout, erreur de connexion, erreur serveur Telegram temporaire).
    Sans ce retry, une alerte peut se perdre silencieusement si l'API
    Telegram met plus de quelques secondes à répondre (cas observé: read
    timeout après 10s sur un pic de charge).
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("Telegram non configuré (token/chat_id manquant) — message non envoyé:\n%s", message)
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"

    for attempt in range(1, retries + 1):
        try:
            r = requests.post(
                url,
                json={"chat_id": config.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
                timeout=15,
            )
            if r.status_code == 200:
                if attempt > 1:
                    log.info("Envoi Telegram réussi à la tentative %d/%d", attempt, retries)
                return
            log.error("Erreur envoi Telegram (%s) tentative %d/%d: %s", r.status_code, attempt, retries, r.text)
        except Exception as e:
            log.error("Exception envoi Telegram tentative %d/%d: %s", attempt, retries, e)

        if attempt < retries:
            time.sleep(2)

    log.error("Échec définitif envoi Telegram après %d tentatives — message perdu:\n%s", retries, message)


def format_alert(symbol: str, avg_z: float, per_exchange: dict, oi_aggregate: dict, per_exchange_oi: dict, direction: str, ts_str: str) -> str:
    """
    per_exchange: {exchange: {"z_combined":..., "z_price":..., "z_volume":...}}
    oi_aggregate: {"variation_pct": float, "notional_usd": float}
    per_exchange_oi: {exchange: {"variation_pct": float}}
    """
    lines = []
    lines.append(f"🚨 <b>ALERTE Z-SCORE MULTI-EXCHANGE</b> 🚨")
    lines.append(f"Paire: <b>{symbol}</b>")
    lines.append(f"Heure: {ts_str} UTC")
    lines.append(f"Direction probable: <b>{direction}</b>")
    lines.append("")

    score100 = zscore_to_score100(avg_z)
    lines.append(f"🧮 Score composite: <b>{score100:.1f}/100</b>")
    lines.append(f"📊 Z-score moyen brut (déclencheur): <b>{avg_z:.2f}</b> (seuil {config.ALERT_THRESHOLD:.2f})")
    lines.append("Détail par exchange (score /100 · combiné brut / prix / volume):")
    for ex in config.EXCHANGES:
        data = per_exchange.get(ex)
        if data is None:
            lines.append(f"  • {ex.capitalize()}: n/d (données indisponibles ce cycle)")
        else:
            ex_score100 = zscore_to_score100(data["z_combined"])
            lines.append(
                f"  • {ex.capitalize()}: {ex_score100:.1f}/100  "
                f"(brut {data['z_combined']:.2f} · prix {data['z_price']:.2f} / volume {data['z_volume']:.2f})"
            )

    lines.append("")
    lines.append(f"💰 Open Interest agrégé (Binance+Bybit+OKX+Bitget): "
                  f"<b>{oi_aggregate['variation_pct']:+.2f}%</b>")
    lines.append("Détail OI par exchange:")
    for ex in config.EXCHANGES:
        data = per_exchange_oi.get(ex)
        if data is None:
            lines.append(f"  • {ex.capitalize()}: n/d")
        else:
            lines.append(f"  • {ex.capitalize()}: {data['variation_pct']:+.2f}%")

    return "\n".join(lines)
