"""Bot Leboncoin -> Discord. Tourne tout seul sur GitHub Actions (un passage par lancement)."""
import json
import os
import re
import statistics
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

# ============== A MODIFIER (directement sur GitHub) ==============
# Une recherche = UN modèle précis. Colle l'URL copiée depuis Leboncoin.
RECHERCHES = {
    "PS5": "https://www.leboncoin.fr/recherche?text=ps5&sort=time&order=desc",
}
REMISE_MIN = 0.25       # au moins 25 % sous la médiane
MARGE_MIN_EUROS = 30    # marge nette minimale
FRAIS_REVENTE = 0.05    # commission estimée
FRAIS_FIXES = 8         # envoi, emballage
# =================================================================

WEBHOOK = os.environ["DISCORD_WEBHOOK"]
SEEN = Path("seen.json")
vues = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()


def discord(texte):
    requests.post(WEBHOOK, json={"content": texte}, timeout=15)


def recuperer(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page.content(), re.S)
    if not m:
                raise RuntimeError(f"Pas de données. Titre : {page.title()!r} | début : {page.content()[:300]!r}")
    ads = json.loads(m.group(1))["props"]["pageProps"]["searchData"]["ads"]
    out = []
    for ad in ads:
        prix = ad.get("price")
        prix = prix[0] if isinstance(prix, list) and prix else prix
        if prix:
            out.append({
                "id": str(ad["list_id"]),
                "titre": ad.get("subject", ""),
                "prix": float(prix),
                "url": ad.get("url") or f"https://www.leboncoin.fr/ad/x/{ad['list_id']}",
                "ville": (ad.get("location") or {}).get("city", ""),
            })
    return out


def analyser(nom, annonces):
    prix = [a["prix"] for a in annonces if a["prix"] > 5]
    if len(prix) < 8:
        print(f"[{nom}] pas assez d'annonces ({len(prix)})")
        return
    mediane = statistics.median(prix)
    for a in annonces:
        if a["id"] in vues:
            continue
        vues.add(a["id"])
        marge = mediane * (1 - FRAIS_REVENTE) - FRAIS_FIXES - a["prix"]
        remise = 1 - a["prix"] / mediane
        if remise >= REMISE_MIN and marge >= MARGE_MIN_EUROS:
            discord(
                f"🔥 **{nom}** : {a['titre']}\n"
                f"Prix : **{a['prix']:.0f} €** (médiane {mediane:.0f} €, -{remise*100:.0f} %)\n"
                f"Marge estimée : ~{marge:.0f} € · 📍 {a['ville']}\n{a['url']}"
            )
            print(f"[{nom}] alerte : {a['titre']}")


erreurs = 0
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        locale="fr-FR",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    )
    page = ctx.new_page()
    for nom, url in RECHERCHES.items():
        try:
            analyser(nom, recuperer(page, url))
        except Exception as e:
            erreurs += 1
            print(f"[{nom}] erreur : {e}")
    browser.close()

SEEN.write_text(json.dumps(sorted(vues)[-5000:]))
if erreurs == len(RECHERCHES):
    raise SystemExit(1)  # le run apparaît en rouge dans l'onglet Actions
