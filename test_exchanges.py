"""
Script de DIAGNOSTIC RÉSEAU — à lancer AVANT de déployer le bot 24/24.

Ce script interroge chaque exchange une fois pour chaque paire et affiche
le résultat brut. Le but : vérifier à l'œil que les chiffres sont
cohérents avec la réalité (comparer avec le site web de l'exchange)
AVANT de faire confiance aux alertes automatiques.

Je n'ai pas pu tester ces appels en conditions réelles depuis mon
environnement de développement (accès réseau restreint). Le code est
écrit à partir de la documentation officielle de chaque API, mais les
schémas de réponse peuvent changer — lance impérativement ce script en
premier, sur Railway ou en local, et regarde si tout te semble cohérent
avant de compter dessus pour de vraies décisions.

Usage : python3 test_exchanges.py
"""
import config
from exchanges import ADAPTERS


def main():
    print("=" * 70)
    print("DIAGNOSTIC — vérifie ces chiffres contre le site web de chaque")
    print("exchange avant de faire confiance aux alertes automatiques.")
    print("=" * 70)

    for symbol in config.SYMBOLS:
        print(f"\n### {symbol} ###")
        for ex in config.EXCHANGES:
            adapter = ADAPTERS[ex]
            ex_symbol = config.EXCHANGE_SYMBOL_MAP[ex][symbol]

            print(f"\n  -- {ex.upper()} (symbole: {ex_symbol}) --")
            try:
                kline = adapter.fetch_kline(ex_symbol)
                print(f"     Kline OK -> close={kline['close']}, volume={kline['volume']}, ts={kline['ts']}")
            except Exception as e:
                print(f"     ❌ Kline ÉCHEC: {e}")

            try:
                oi = adapter.fetch_oi(ex_symbol)
                print(f"     OI    OK -> oi_qty={oi['oi_qty']}, ts={oi['ts']}")
            except Exception as e:
                print(f"     ❌ OI ÉCHEC: {e}")

    print("\n" + "=" * 70)
    print("Si tout est '✅' (pas de ÉCHEC) et que les valeurs te semblent")
    print("réalistes, le bot est prêt à tourner en continu. Sinon, corrige")
    print("l'adaptateur concerné dans exchanges/<nom>.py avant de lancer main.py.")
    print("=" * 70)


if __name__ == "__main__":
    main()
