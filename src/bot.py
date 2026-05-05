from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
import json
import os
import random
import re
from datetime import datetime
from random_username.generate import generate_username
from email_service_copy import GuerrillaMailClient


# Config 

SITE_URL      = os.environ.get("SITE_URL", "https://www.wiki-masters.com/")
HEADLESS      = os.environ.get("HEADLESS", "true").lower() == "true"
REPORTS_DIR   = "reports"
SCREENSHOTS_DIR = "screenshots"
BOTS_DB_PATH  = os.path.join(REPORTS_DIR, "bots_db.json")


# Helpers 

def load_bots_db() -> dict:
    """Load the persistent bots database."""
    if os.path.exists(BOTS_DB_PATH):
        with open(BOTS_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"bots": []}


def save_bots_db(db: dict):
    """Save the persistent bots database."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(BOTS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def safe_goto(page: Page, url: str, retries: int = 3, timeout: int = 15000):
    """Navigate to a URL with retry logic for page load errors."""
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")

            # Detect "This page couldn't load" error screen
            error_locator = page.locator("text=This page couldn't load")
            if error_locator.is_visible():
                raise Exception("Page load error detected (blank error screen)")

            return  # success

        except Exception as e:
            print(f"⚠️  Navigation attempt {attempt}/{retries} failed: {e}")
            if attempt == retries:
                raise
            page.wait_for_timeout(2000 * attempt)  # backoff


def get_counter_value(page: Page) -> int:
    """Read the packet counter (e.g. '8 / 10' → 8)."""
    locator = page.locator(
        '//span[contains(@class, "color-accent")'
        ' and string-length(normalize-space(text())) <= 2'
        ' and translate(normalize-space(text()), "0123456789", "") = ""]'
    )
    locator.wait_for(state="visible", timeout=10000)
    return int(locator.inner_text().strip())


def open_paquet(page: Page):
    """Open one packet and reveal all 4 cards, then continue."""
    btn_open   = page.get_by_role("button", name="Ouvrir un paquet Ouvrir")
    btn_next   = page.locator(".flex.items-center.gap-4 > button:nth-child(3)")
    btn_continue = page.get_by_role("button", name="Continuer")

    btn_open.wait_for(state="visible", timeout=20000)
    btn_open.click()

    for _ in range(4):
        delay = random.randint(50, 250)
        page.wait_for_timeout(delay)
        btn_next.wait_for(state="visible", timeout=10000)
        btn_next.click()

    page.wait_for_timeout(random.randint(50, 200))
    btn_continue.click()


def screenshot(page: Page, name: str):
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOTS_DIR, f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    page.screenshot(path=path)
    return path



def register_new_bot(page: Page) -> dict:
    """Register a new account and return bot credentials dict."""
    username = generate_username(1)[0]
    gm       = GuerrillaMailClient(prefix=username)
    email    = gm.create_email()
    password = "TestPassword123!"

    print(f"📧 Email: {email}  |  👤 Username: {username}")
    known_ids = gm.snapshot_mail_ids()

    safe_goto(page, SITE_URL)

    page.get_by_role("textbox", name="Nom d'utilisateur").fill(username)
    page.get_by_role("textbox", name="Adresse courriel").fill(email)
    page.get_by_role("textbox", name="Mot de passe").fill(password)
    page.get_by_role("checkbox", name="Je confirme avoir au moins 18").check()
    page.get_by_role("button", name="Créer mon compte").click()

    print("⏳ Waiting for verification email…")
    mail = gm.wait_for_matching_email(known_ids=known_ids)
    code = gm.get_latest_code(mail)
    assert code, "❌ No verification code received"

    page.get_by_role("textbox", name="Code de vérification").fill(code)
    page.get_by_role("button", name="Vérifier et continuer").click()

    return {
        "id":         datetime.now().strftime("%Y%m%d%H%M%S"),
        "username":   username,
        "email":      email,
        "password":   password,
        "created_at": datetime.now().isoformat(),
        "sessions":   []
    }


def open_all_paquets(page: Page) -> dict:
    """Navigate to Paquets and open every available packet. Returns session stats."""
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
                break

            open_paquet(page)
            paquets_opened += 1
            page.wait_for_timeout(100)

        except PlaywrightTimeout as e:
            msg = f"Timeout opening paquet #{paquets_opened + 1}: {e}"
            errors.append(msg)
            print(f"⚠️  {msg}")
            # Try to recover by reloading
            try:
                safe_goto(page, page.url)
                page.wait_for_timeout(2000)
            except Exception:
                break

        except Exception as e:
            msg = f"Error on paquet #{paquets_opened + 1}: {e}"
            errors.append(msg)
            print(f"❌ {msg}")
            break

    return {"paquets_opened": paquets_opened, "errors": errors}


# Main bot runner 

def run_bot():
    db      = load_bots_db()
    session = {
        "date":           datetime.now().isoformat(),
        "actions":        [],
        "errors":         [],
        "paquets_opened": 0,
        "screenshots":    []
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page    = browser.new_page()

        try:
            # 1. Register
            bot_data = register_new_bot(page)
            session["actions"].append("✅ Compte créé et vérifié")

            # 2. Screenshot post-login
            path = screenshot(page, f"login_{bot_data['username']}")
            session["screenshots"].append(path)
            session["actions"].append("✅ Screenshot post-login")

            # 3. Open all packets
            stats = open_all_paquets(page)
            session["paquets_opened"] = stats["paquets_opened"]
            session["errors"].extend(stats["errors"])
            session["actions"].append(f"✅ {stats['paquets_opened']} paquets ouverts")

            # 4. Screenshot collection
            page.get_by_role("link", name="Collection").click()
            page.get_by_role("heading", name="Collection").wait_for(state="visible", timeout=10000)
            path = screenshot(page, f"collection_{bot_data['username']}")
            session["screenshots"].append(path)
            session["actions"].append("✅ Screenshot collection")

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

    # 5. Persist bot + session
    bot_data["sessions"].append(session)
    db["bots"].append(bot_data)
    save_bots_db(db)

    # 6. Individual report
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(
        REPORTS_DIR,
        f"report_{bot_data.get('username', 'unknown')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"bot": bot_data, "last_session": session}, f, ensure_ascii=False, indent=2)

    # 7. Console summary
    print("\n📋 RAPPORT :")
    for action in session["actions"]:
        print(f"  {action}")
    if session["errors"]:
        print("\n⚠️  ERREURS :")
        for err in session["errors"]:
            print(f"  {err}")
    print(f"\n📦 Paquets ouverts : {session['paquets_opened']}")

    return {"bot": bot_data, "session": session}


if __name__ == "__main__":
    run_bot()