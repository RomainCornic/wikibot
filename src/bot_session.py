import logging
import os
from datetime import datetime

from playwright.sync_api import Page, sync_playwright

from bot_helper import (
    BOTS_DB_PATH,
    COOKIES_DIR,
    HEADLESS,
    LOGIN_URL,
    SITE_URL,
    TIMEOUT,
    load_bots_db,
    open_all_paquets,
    safe_goto,
    save_bots_db,
    screenshot,
)
from logger import setup_logger

setup_logger(
    name="my_app",
    level=logging.DEBUG,
    log_file="src/logs/bot_sessions.log",
)
logger = logging.getLogger(__name__)


def save_cookies(context, username: str) -> str:
    """Sauvegarde le storage state complet (cookies + localStorage)."""
    os.makedirs(COOKIES_DIR, exist_ok=True)
    path = os.path.join(COOKIES_DIR, f"{username}.json")
    context.storage_state(path=path)
    print(f"🍪 Cookies sauvegardés → {path}")
    return path


def load_cookies_context(p, bot: dict):
    """
    Crée un browser context en restaurant les cookies si disponibles.
    Retourne (browser, context, page).
    Priorité : cookies_path du bot → cookies/{username}.json → session vierge
    """
    browser = p.chromium.launch(headless=HEADLESS)

    cookies_path = bot.get("cookies_path")
    if not cookies_path or not os.path.exists(cookies_path):
        # Fallback sur le fichier par nom
        fallback = os.path.join(COOKIES_DIR, f"{bot.get('username', '')}.json")
        cookies_path = fallback if os.path.exists(fallback) else None

    if cookies_path:
        print(f"🍪 Restauration cookies depuis {cookies_path}")
        context = browser.new_context(storage_state=cookies_path)
    else:
        print("🍪 Aucun cookie trouvé — connexion via email/mdp")
        context = browser.new_context()

    page = context.new_page()
    return browser, context, page


# Login


def login(page: Page, context, bot: dict):
    """
    Tente d'abord d'utiliser les cookies existants.
    Si la session est expirée ou absente, bascule sur email/mdp.
    """
    email = bot["email"]
    password = bot["password"]
    username = bot.get("username", email)

    # Aller sur le site — si les cookies sont valides, on sera déjà connecté
    safe_goto(page, SITE_URL)

    already_logged = page.get_by_role("link", name="Paquets").is_visible()

    if already_logged:
        print("✅ Session restaurée via cookies — pas besoin de se reconnecter")
        return

    # Cookies expirés ou absents → login classique
    print(f"🔐 Cookies invalides — connexion avec {email}…")
    safe_goto(page, LOGIN_URL)

    page.get_by_role("textbox", name="Adresse courriel").fill(email)
    page.get_by_role("textbox", name="Mot de passe").fill(password)
    page.get_by_role("button", name="Se connecter").click()

    page.get_by_role("link", name="Paquets").wait_for(state="visible", timeout=15000)
    print("✅ Connecté via email/mdp")

    # Sauvegarder les nouveaux cookies
    save_cookies(context, username)


# Session runner


def run_session(bot_index: int = None, email: str = None):
    """
    Relance une session pour un bot existant.
    Utilise bot_index (position dans bots_db) ou email pour identifier le bot.
    Si ni l'un ni l'autre n'est fourni, relance le dernier bot enregistré.
    """
    db = load_bots_db()
    bots = db.get("bots", [])

    if not bots:
        print("❌ Aucun bot dans bots_db.json — lance d'abord bot.py")
        return

    # Trouver le bot cible
    if email:
        bot = next((b for b in bots if b["email"] == email), None)
        if not bot:
            print(f"❌ Aucun bot avec l'email : {email}")
            return
        bot_index = bots.index(bot)
    elif bot_index is not None:
        if bot_index < 0 or bot_index >= len(bots):
            print(f"❌ Index invalide : {bot_index} (0–{len(bots) - 1} disponibles)")
            return
        bot = bots[bot_index]
    else:
        bot_index = len(bots) - 1
        bot = bots[bot_index]

    print(f"🤖 Bot cible : {bot['username']} ({bot['email']})")

    session = {
        "date": datetime.now().isoformat(),
        "type": "reconnection",
        "actions": [],
        "errors": [],
        "paquets_opened": 0,
        "screenshots": [],
    }

    with sync_playwright() as p:
        browser, context, page = load_cookies_context(p, bot)
        page = browser.new_page()

        try:
            # 1. Login
            login(page, context, bot)
            session["actions"].append("✅ Connexion réussie")

            path = screenshot(page, f"login_{bot['username']}")
            session["screenshots"].append(path)

            # 2. Ouvrir tous les paquets
            stats = open_all_paquets(page)
            session["paquets_opened"] = stats["paquets_opened"]
            session["errors"].extend(stats["errors"])
            session["actions"].append(f"✅ {stats['paquets_opened']} paquets ouverts")

            # 3. Screenshot collection
            page.get_by_role("link", name="Collection").click()
            page.get_by_role("heading", name="Collection").wait_for(
                state="visible", timeout=TIMEOUT
            )
            path = screenshot(page, f"collection_{bot['username']}")
            session["screenshots"].append(path)
            session["actions"].append("✅ Screenshot collection")

            # 4. Sauvegarder les cookies mis à jour
            cookies_path = save_cookies(context, bot["username"])
            db["bots"][bot_index]["cookies_path"] = cookies_path
            session["actions"].append("✅ Cookies mis à jour")

        except Exception as e:
            msg = f"❌ Erreur fatale : {e}"
            session["errors"].append(msg)
            print(msg)
            try:
                path = screenshot(page, "erreur")
                session["screenshots"].append(path)
            except Exception:
                pass

        finally:
            browser.close()
            browser.close()

    # 4. Mise à jour de la base de données
    db["bots"][bot_index].setdefault("sessions", []).append(session)
    save_bots_db(db)
    print(f"💾 Base de données mise à jour ({BOTS_DB_PATH})")

    # 5. Résumé console
    print("\n📋 RÉSUMÉ DE SESSION :")
    for action in session["actions"]:
        print(f"  {action}")
    if session["errors"]:
        print("\n⚠️  ERREURS :")
        for err in session["errors"]:
            print(f"  {err}")
    print(f"\n📦 Paquets ouverts : {session['paquets_opened']}")

    return session


def run_all_bots():
    """Relance une session pour TOUS les bots enregistrés."""
    db = load_bots_db()
    bots = db.get("bots", [])

    if not bots:
        print("❌ Aucun bot dans bots_db.json")
        return

    print(f"🚀 Lancement de {len(bots)} bot(s)…\n")
    for i, bot in enumerate(bots):
        print(f"\n{'─' * 50}")
        print(f"[{i + 1}/{len(bots)}] {bot['username']}")
        print(f"{'─' * 50}")
        run_session(bot_index=i)


# Entry point

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Relance une session WikiMasters")
    parser.add_argument("--email", type=str, help="Email du bot à relancer")
    parser.add_argument(
        "--index", type=int, help="Index du bot dans bots_db.json (0-based)"
    )
    parser.add_argument("--all", action="store_true", help="Relancer tous les bots")
    args = parser.parse_args()

    if args.all:
        run_all_bots()
    elif args.email:
        run_session(email=args.email)
    elif args.index is not None:
        run_session(bot_index=args.index)
    else:
        # Par défaut : dernier bot enregistré
        run_session()
