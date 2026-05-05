from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
import json
import os
import random
import re
from datetime import datetime
from random_username.generate import generate_username
from email_service_copy import GuerrillaMailClient
from bot_helper import open_all_paquets,safe_goto,load_bots_db,screenshot,save_bots_db,BOTS_DB_PATH,SCREENSHOTS_DIR,REPORTS_DIR,HEADLESS,LOGIN_URL,SITE_URL,get_counter_value,open_paquet









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