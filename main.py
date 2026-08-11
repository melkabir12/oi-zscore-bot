"""
Point d'entrée du bot — à lancer sur Railway comme "worker" (pas de serveur
web nécessaire, juste `python3 main.py` en process de fond, 24/24).

Deux boucles asynchrones tournent en parallèle :
1. Boucle Z-score : toutes les ~60s, récupère la dernière bougie 1 min
   close sur les 4 exchanges × 3 paires, calcule les Z-scores, déclenche
   une alerte si la moyenne inter-exchange dépasse le seuil.
2. Boucle OI : toutes les 5 min, récupère l'OI courant sur les 4
   exchanges × 3 paires, calcule les variations (agrégée + par exchange).

NOUVEAU: ce bot reste silencieux (pas d'analyse, pas d'appel exchange) pour
un coin donné tant que le bot volume primaire n'a pas déclenché d'alerte
SUR CE COIN (flag par coin via Upstash Redis, voir redis_gate.py).
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

import config
import state as state_module
from exchanges import ADAPTERS
from zscore import SymbolExchangeStats
from oi_tracker import OiSeries, AggregateOiSeries
from telegram_alert import send_telegram, format_alert
from http_client import ExchangeFetchError
from redis_gate import is_trigger_active

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("main")


class Bot:
    def __init__(self):
        saved = state_module.load_state()

        self.zscore_stats = {}
        for ex in config.EXCHANGES:
            for sym in config.SYMBOLS:
                s = SymbolExchangeStats()
                s.load_state(saved["zscore"].get(f"{ex}:{sym}"))
                self.zscore_stats[(ex, sym)] = s

        self.oi_series = {}
        for ex in config.EXCHANGES:
            for sym in config.SYMBOLS:
                o = OiSeries()
                o.load_state(saved["oi"].get(f"{ex}:{sym}"))
                self.oi_series[(ex, sym)] = o

        self.oi_aggregate = {}
        for sym in config.SYMBOLS:
            a = AggregateOiSeries()
            a.load_state(saved["oi_aggregate"].get(sym))
            self.oi_aggregate[sym] = a

        self.last_price = {}
        self.last_oi_result = {(ex, sym): None for ex in config.EXCHANGES for sym in config.SYMBOLS}
        self.last_oi_aggregate_result = {sym: None for sym in config.SYMBOLS}

        self._was_active = {sym: False for sym in config.SYMBOLS}

    def persist(self):
        payload = {
            "zscore": {f"{ex}:{sym}": s.to_state() for (ex, sym), s in self.zscore_stats.items()},
            "oi": {f"{ex}:{sym}": s.to_state() for (ex, sym), s in self.oi_series.items()},
            "oi_aggregate": {sym: a.to_state() for sym, a in self.oi_aggregate.items()},
        }
        state_module.save_state(payload)

    async def kline_loop(self):
        while True:
            cycle_start = time.time()

            for symbol in config.SYMBOLS:
                active = await asyncio.to_thread(is_trigger_active, symbol)
                if not active:
                    self._was_active[symbol] = False
                    continue

                if not self._was_active[symbol]:
                    log.info("[%s] Trigger actif détecté — activation de l'analyse Z-score/OI.", symbol)
                    self._was_active[symbol] = True

                per_exchange = {}
                for ex in config.EXCHANGES:
                    ex_symbol = config.EXCHANGE_SYMBOL_MAP[ex][symbol]
                    adapter = ADAPTERS[ex]
                    try:
                        kline = await asyncio.to_thread(adapter.fetch_kline, ex_symbol)
                    except (ExchangeFetchError, ValueError, KeyError, TypeError) as e:
                        log.warning("[%s/%s] Échec récupération kline: %s", ex, symbol, e)
                        continue

                    self.last_price[(ex, symbol)] = kline["close"]
                    stats = self.zscore_stats[(ex, symbol)]

                    if stats.last_ts == kline["ts"]:
                        if stats.ready:
                            per_exchange[ex] = {
                                "z_price": stats.last_z_price,
                                "z_volume": stats.last_z_volume,
                                "z_combined": stats.last_z_combined,
                            }
                        continue

                    res = stats.update(kline["ts"], kline["close"], kline["volume"])
                    log.info(
                        "[%s/%s] close=%.4f vol=%.4f z_price=%.2f z_volume=%.2f z_combined=%.2f ready=%s",
                        ex, symbol, kline["close"], kline["volume"],
                        res["z_price"], res["z_volume"], res["z_combined"], res["ready"],
                    )
                    if res["ready"]:
                        per_exchange[ex] = {
                            "z_price": res["z_price"],
                            "z_volume": res["z_volume"],
                            "z_combined": res["z_combined"],
                        }

                self._maybe_alert(symbol, per_exchange)

            self.persist()
            elapsed = time.time() - cycle_start
            await asyncio.sleep(max(1.0, config.KLINE_POLL_INTERVAL_SEC - elapsed))

    def _maybe_alert(self, symbol: str, per_exchange: dict):
        if len(per_exchange) < config.MIN_EXCHANGES_FOR_ALERT:
            return

        avg_z = sum(v["z_combined"] for v in per_exchange.values()) / len(per_exchange)
        if avg_z < config.ALERT_THRESHOLD:
            return

        signed = [v["z_price"] for v in per_exchange.values()]
        avg_signed = sum(signed) / len(signed)
        if avg_signed > 0:
            direction = "hausse anormale — probable liquidation de SHORTS"
        elif avg_signed < 0:
            direction = "baisse anormale — probable liquidation de LONGS"
        else:
            direction = "signal neutre"

        oi_aggregate = self.last_oi_aggregate_result.get(symbol) or {"variation_pct": 0.0}
        per_exchange_oi = {
            ex: self.last_oi_result.get((ex, symbol))
            for ex in config.EXCHANGES
        }

        ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        msg = format_alert(
            symbol=symbol,
            avg_z=avg_z,
            per_exchange=per_exchange,
            oi_aggregate={"variation_pct": oi_aggregate.get("variation_pct") or 0.0},
            per_exchange_oi=per_exchange_oi,
            direction=direction,
            ts_str=ts_str,
        )
        log.info("ALERTE déclenchée pour %s (Z moyen=%.2f)", symbol, avg_z)
        send_telegram(msg)

    async def oi_loop(self):
        while True:
            cycle_start = time.time()

            for symbol in config.SYMBOLS:
                active = await asyncio.to_thread(is_trigger_active, symbol)
                if not active:
                    continue

                per_exchange_results = {}
                for ex in config.EXCHANGES:
                    ex_symbol = config.EXCHANGE_SYMBOL_MAP[ex][symbol]
                    adapter = ADAPTERS[ex]
                    price = self.last_price.get((ex, symbol))
                    try:
                        oi = await asyncio.to_thread(adapter.fetch_oi, ex_symbol)
                        if price is None:
                            log.info("[%s/%s] OI reçu mais pas encore de prix connu, notionnel reporté au prochain cycle", ex, symbol)
                            per_exchange_results[ex] = None
                            continue
                        result = self.oi_series[(ex, symbol)].update(oi["ts"], oi["oi_qty"], price)
                        per_exchange_results[ex] = result
                        self.last_oi_result[(ex, symbol)] = result
                        log.info(
                            "[%s/%s] OI=%.4f prix=%.4f notionnel=%.0f$ variation=%s",
                            ex, symbol, oi["oi_qty"], price, result["notional_usd"],
                            f"{result['variation_pct']:+.2f}%" if result["variation_pct"] is not None else "n/d",
                        )
                    except (ExchangeFetchError, ValueError, KeyError, TypeError) as e:
                        log.warning("[%s/%s] Échec récupération OI: %s", ex, symbol, e)
                        per_exchange_results[ex] = None

                agg = self.oi_aggregate[symbol].update(per_exchange_results)
                self.last_oi_aggregate_result[symbol] = agg
                log.info(
                    "[AGGREGAT/%s] notionnel=%.0f$ (%d/%d exchanges) variation=%s",
                    symbol, agg["notional_usd"], agg["n_exchanges"], len(config.EXCHANGES),
                    f"{agg['variation_pct']:+.2f}%" if agg["variation_pct"] is not None else "n/d",
                )

            self.persist()
            elapsed = time.time() - cycle_start
            await asyncio.sleep(max(1.0, config.OI_POLL_INTERVAL_SEC - elapsed))


async def main():
    log.info("Démarrage du bot Z-score + OI multi-exchange (BTC/ETH/XRP)...")
    log.info(
        "Config: fenêtre=%d, seuil alerte=%.2f, min exchanges=%d, poll OI=%ds",
        config.ZSCORE_WINDOW, config.ALERT_THRESHOLD,
        config.MIN_EXCHANGES_FOR_ALERT, config.OI_POLL_INTERVAL_SEC,
    )
    send_telegram(
        f"✅ Bot Z-score + OI démarré — paires: {', '.join(config.SYMBOLS)} | "
        f"exchanges: {', '.join(config.EXCHANGES)} | seuil: {config.ALERT_THRESHOLD} | "
        f"en veille jusqu'à déclenchement du bot volume primaire (par coin)"
    )
    bot = Bot()
    await asyncio.gather(bot.kline_loop(), bot.oi_loop())


if __name__ == "__main__":
    asyncio.run(main())
