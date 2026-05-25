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

## Déploiement
L'application est déployée sur [Render](https://render.com).
