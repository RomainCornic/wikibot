import json
import os
import random
from datetime import datetime

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

# ─── Config ───────────────────────────────────────────────────────────────────

SITE_URL = os.environ.get("SITE_URL", "https://www.wiki-masters.com/")
LOGIN_URL = SITE_URL + "login"
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"
REPORTS_DIR = "reports"
SCREENSHOTS_DIR = "screenshots"
COOKIES_DIR = "cookies"
BOTS_DB_PATH = os.path.join(REPORTS_DIR, "bots_db.json")


# ─── DB ───────────────────────────────────────────────────────────────────────


def load_bots_db() -> dict:
    if os.path.exists(BOTS_DB_PATH):
        with open(BOTS_DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"bots": []}


def save_bots_db(db: dict):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(BOTS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ─── Navigation ───────────────────────────────────────────────────────────────


def safe_goto(page: Page, url: str, retries: int = 3, timeout: int = 15000):
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            if page.locator("text=This page couldn't load").is_visible():
                raise Exception("Page load error detected")
            return
        except Exception as e:
            print(f"⚠️  Navigation attempt {attempt}/{retries} failed: {e}")
            if attempt == retries:
                raise
            page.wait_for_timeout(2000 * attempt)


def screenshot(page: Page, name: str) -> str:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    path = os.path.join(
        SCREENSHOTS_DIR, f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    )
    page.screenshot(path=path)
    return path


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


# ─── Login ────────────────────────────────────────────────────────────────────


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


# ─── Paquets ──────────────────────────────────────────────────────────────────


def get_counter_value(page: Page) -> int:
    locator = page.locator(
        '//span[contains(@class, "color-accent")'
        " and string-length(normalize-space(text())) <= 2"
        ' and translate(normalize-space(text()), "0123456789", "") = ""]'
    )
    locator.wait_for(state="visible", timeout=10000)
    return int(locator.inner_text().strip())


def open_paquet(page: Page):
    btn_open = page.get_by_role("button", name="Ouvrir un paquet Ouvrir")
    btn_next = page.locator(".flex.items-center.gap-4 > button:nth-child(3)")
    btn_continue = page.get_by_role("button", name="Continuer")

    btn_open.wait_for(state="visible", timeout=20000)
    btn_open.click()

    for _ in range(4):
        page.wait_for_timeout(random.randint(50, 250))
        btn_next.wait_for(state="visible", timeout=10000)
        btn_next.click()

    page.wait_for_timeout(random.randint(50, 200))
    btn_continue.click()


def open_all_paquets(page: Page) -> dict:
    page.get_by_role("link", name="Paquets").wait_for(state="visible", timeout=10000)
    page.get_by_role("link", name="Paquets").click()
    page.wait_for_timeout(1000)

    paquets_opened = 0
    errors = []

    while True:
        try:
            counter = get_counter_value(page)
            print(f"📦 Paquets restants : {counter}")
            if counter <= 0:
                print("✅ Tous les paquets ouverts")
                break

            open_paquet(page)
            paquets_opened += 1
            page.wait_for_timeout(100)

        except PlaywrightTimeout as e:
            msg = f"Timeout paquet #{paquets_opened + 1}: {e}"
            errors.append(msg)
            print(f"⚠️  {msg}")
            try:
                safe_goto(page, page.url)
                page.wait_for_timeout(2000)
            except Exception:
                break

        except Exception as e:
            msg = f"Erreur paquet #{paquets_opened + 1}: {e}"
            errors.append(msg)
            print(f"❌ {msg}")
            break

    return {"paquets_opened": paquets_opened, "errors": errors}


# ─── Session runner ───────────────────────────────────────────────────────────


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

        try:
            # 1. Login (cookies ou email/mdp)
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
            context.close()
            browser.close()

    # Mise à jour de la base de données
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


# ─── Entry point ─────────────────────────────────────────────────────────────

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
