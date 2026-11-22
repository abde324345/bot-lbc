"""Bot Vinted -> Discord. Tourne sur GitHub Actions (un passage par lancement)."""
import json
import os
import statistics
from pathlib import Path
from urllib.parse import quote

import requests
from playwright.sync_api import sync_playwright

# ============== A MODIFIER ==============
# Nom affiché : mot(s) recherché(s). Un modèle précis par ligne.
RECHERCHES = {
    "Air Force 1": "nike air force 1",
    "Jordan 1": "air jordan 1",
}
REMISE_MIN = 0.30       # au moins 30 % sous la médiane
MARGE_MIN_EUROS = 15    # marge minimale
FRAIS_REVENTE = 0.0     # Vinted ne prend rien au vendeur
FRAIS_FIXES = 3         # emballage, etc.
# ========================================

WEBHOOK = os.environ["DISCORD_WEBHOOK"]
SEEN = Path("seen.json")
vues = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()


def discord(texte):
    requests.post(WEBHOOK, json={"content": texte}, timeout=15)


def recuperer(page, texte):
    page.goto("https://www.vinted.fr", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)
    url = (
        "https://www.vinted.fr/api/v2/catalog/items"
        f"?search_text={quote(texte)}&order=newest_first&per_page=96"
    )
    r = page.context.request.get(url, headers={"Accept": "application/json"})
    if r.status != 200:
        raise RuntimeError(f"Vinted a répondu {r.status} : {r.text()[:200]!r}")
    out = []
    for it in r.json().get("items", []):
        prix = it.get("price")
        if isinstance(prix, dict):
            prix = prix.get("amount")
        try:
            prix = float(prix)
        except (TypeError, ValueError):
            continue
        out.append({
            "id": str(it["id"]),
            "titre": it.get("title", ""),
            "prix": prix,
            "marque": it.get("brand_title", ""),
            "taille": it.get("size_title", ""),
            "url": it.get("url") or f"https://www.vinted.fr/items/{it['id']}",
        })
    return out


def analyser(nom, annonces):
    prix = [a["prix"] for a in annonces if a["prix"] > 3]
    if len(prix) < 10:
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
                f"Marge estimée : ~{marge:.0f} € · {a['marque']} · taille {a['taille']}\n{a['url']}"
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
    for nom, texte in RECHERCHES.items():
        try:
            analyser(nom, recuperer(page, texte))
        except Exception as e:
            erreurs += 1
            print(f"[{nom}] erreur : {e}")
    browser.close()

SEEN.write_text(json.dumps(sorted(vues)[-5000:]))
if erreurs == len(RECHERCHES):
    raise SystemExit(1)
