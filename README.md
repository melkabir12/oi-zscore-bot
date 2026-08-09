# Bot Z-score + Open Interest multi-exchange (BTC/ETH/XRP)

Surveille en continu BTC, ETH et XRP sur **Binance, Bybit, OKX et Bitget**
(perpetuals), calcule un Z-score prix+volume par exchange, et alerte sur
Telegram quand la **moyenne** des Z-scores des exchanges dépasse un seuil
— accompagné de l'**Open Interest agrégé** (les 4 exchanges) et détaillé
par exchange.

## ⚠️ À faire AVANT tout déploiement 24/24

Je n'ai pas pu tester les appels réseau vers Binance/Bybit/OKX/Bitget
depuis mon environnement de développement (accès bloqué). Le code des
4 adaptateurs (`exchanges/*.py`) est écrit à partir de la documentation
officielle de chaque API, mais les schémas de réponse évoluent parfois.

**Lance d'abord le diagnostic, en local ou sur Railway :**

```bash
pip install -r requirements.txt
python3 test_exchanges.py
```

Ça affiche, pour chaque exchange × chaque paire, le prix/volume et l'OI
bruts récupérés. Compare visuellement avec le site de l'exchange. Si un
adaptateur affiche une erreur ou un chiffre incohérent, corrige-le dans
`exchanges/<nom>.py` avant de lancer `main.py` en continu — c'est
l'adaptateur Bitget (OI) qui a le schéma le moins garanti, regarde-le
en premier.

Les tests **mathématiques** (formule du Z-score elle-même), eux, sont
déjà vérifiés et ne nécessitent aucun réseau :

```bash
python3 test_math.py
```

## Logique du bot

### Z-score (prix + volume)

Pour chaque paire, sur chaque exchange, à chaque bougie 1 min close :
- `Z_prix` = écart du rendement % par rapport à la moyenne/écart-type
  des 20 dernières bougies (fenêtre glissante)
- `Z_volume` = même calcul sur le volume
- `score combiné` = `0.6 × |Z_prix| + 0.4 × max(Z_volume, 0)`
  (une baisse de volume ne compte pas comme un signal de pic)

**Déclenchement de l'alerte** : la **moyenne** des scores combinés des
exchanges ayant répondu ce cycle doit être **≥ 3** (configurable).

### Open Interest

Toutes les 5 minutes, on récupère l'OI courant (en coin) sur les 4
exchanges, on le convertit en notionnel USD (`OI × dernier prix connu`)
pour pouvoir les additionner de façon cohérente, et on calcule la
variation par rapport au poll précédent — **sans seuil de
classification**, le chiffre brut est toujours affiché (ex: `-0.25%` /
`+0.30%`, toujours 2 décimales).

### Contenu d'une alerte

```
🚨 ALERTE Z-SCORE MULTI-EXCHANGE 🚨
Paire: BTC
Heure: 2026-08-09 14:32:00 UTC
Direction probable: hausse anormale — probable liquidation de SHORTS

📊 Z-score moyen (déclencheur): 3.42 (seuil 3.00)
Détail par exchange (score combiné / prix / volume):
  • Binance: 3.10 (prix 2.80 / volume 3.50)
  • Bybit: 4.05 (prix 3.90 / volume 4.20)
  • Okx: 2.95 (prix 2.60 / volume 3.30)
  • Bitget: 3.58 (prix 3.20 / volume 3.90)

💰 Open Interest agrégé (Binance+Bybit+OKX+Bitget): -0.25%
Détail OI par exchange:
  • Binance: -0.30%
  • Bybit: -0.18%
  • Okx: -0.22%
  • Bitget: -0.31%
```

Une alerte Telegram séparée est envoyée par paire (BTC, ETH, XRP
indépendants).

## Déploiement sur Railway

1. Pousse ce dossier sur un repo GitHub (ou upload direct sur Railway)
2. Sur Railway : **New Project → Deploy from GitHub repo**
3. Railway détecte le `Procfile` et lance `python3 main.py` comme
   process `worker` — pas de port HTTP nécessaire, c'est un process de
   fond pur
4. Variables d'environnement à configurer (Railway → Variables) :
   - `TELEGRAM_BOT_TOKEN` — token de ton bot Telegram
   - `TELEGRAM_CHAT_ID` — ID du chat/canal qui reçoit les alertes
   - `STATE_FILE` — si tu montes un **Volume Railway**, pointe dessus
     (ex: `/data/state.json`) pour que l'historique survive aux
     redeploys. Sinon le bot repart avec un historique vide à chaque
     redeploy (il se reconstitue en ~20 min, pas grave, mais les
     alertes sont suspendues pendant ce temps).
5. Optionnel, tout ajustable sans toucher au code (voir `config.py`
   pour la liste complète) :
   - `ALERT_THRESHOLD` (défaut 3.0)
   - `MIN_EXCHANGES_FOR_ALERT` (défaut 2)
   - `ZSCORE_WINDOW` (défaut 20)
   - `OI_POLL_INTERVAL_SEC` (défaut 300 = 5 min)
   - `W_PRICE` / `W_VOLUME` (pondération du score combiné, défaut 0.6/0.4)

## Limites connues (transparence)

- **CME est exclu** : pas d'API publique gratuite en temps réel pour
  l'Open Interest CME (données officielles payantes ou décalées de 24h
  via CME DataMine). Si tu veux l'intégrer plus tard, ce serait en
  différé (rapport quotidien), pas dans les alertes temps réel.
- L'OI est interrogé par **polling REST** (aucun exchange ne le pousse
  en WebSocket), donc la donnée a jusqu'à 5 minutes de retard par
  rapport à l'instant réel — c'est le compromis validé.
- Les klines sont aussi en **polling REST** (toutes les ~60s), pas en
  WebSocket. Choix délibéré : avec 4 exchanges aux formats de message
  très différents, un WebSocket par exchange est nettement plus
  difficile à garantir sans bug qu'un polling REST simple — la
  priorité donnée était la fiabilité du calcul, pas la latence à la
  seconde près.
- Le schéma de réponse OI de **Bitget** est le moins bien documenté
  publiquement des 4 — l'adaptateur gère plusieurs formats possibles
  et lève une erreur explicite (au lieu d'un chiffre silencieusement
  faux) si aucun ne correspond. À vérifier en priorité avec
  `test_exchanges.py`.
