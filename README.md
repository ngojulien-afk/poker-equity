# Poker Equity Calculator

Application web de calcul d'équité poker, développée avec Flask (Python).

## Fonctionnalités
- Calcul d'équité entre 2+ joueurs (Monte Carlo & énumération complète)
- Analyse par carte de turn et de river
- Parsing de ranges poker (ex: `AKs`, `QQ+`, `JTs-87s`)

## Stack technique
- **Backend** : Python / Flask
- **Moteur** : Monte Carlo + énumération complète (poker_engine.py)
- **Frontend** : HTML/CSS/JS (vanilla)

## Lancer en local
```bash
pip install -r requirements.txt
python app.py
```

## Déploiement (Vercel + Neon)
- **Hébergement** : Vercel (Flask détecté en zéro-config via `requirements.txt` + `app.py`).
- **Base de données** : Neon (Postgres) pour la synchro des ranges entre appareils.
- **Variable d'environnement requise** : `DATABASE_URL` = chaîne de connexion *pooled* Neon.

Sans `DATABASE_URL`, l'appli fonctionne quand même : seules les fonctions de
synchro cloud (Cloud Sync) sont désactivées (les ranges restent en localStorage).
