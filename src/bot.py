from playwright.sync_api import sync_playwright
from email_service import generate_temp_email
import json
import os
from datetime import datetime
from random_username.generate import generate_username
from email_service_copy import GuerrillaMailClient





def run_bot():
    username=generate_username(1)[0]
    gm = GuerrillaMailClient(prefix=username)
    email = gm.create_email()
    print(f"email = {email}")

    actions_log = []
    report = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "email_utilisé": email,
        "actions": [],
        "erreurs": []
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # ← Obligatoire sur GitHub Actions
        page = browser.new_page()
        SITE_URL = os.environ.get("SITE_URL", "https://www.wiki-masters.com/")
        SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "")
        print(SITE_URL)
        try:
            # --- Navigation ---
            page.goto(SITE_URL)
            actions_log.append("✅ Navigation vers la page de login")

            # --- Inscription/Connexion ---
            page.fill("#email", email)
            page.fill("#password", "TestPassword123!")
            page.fill("#username", username)

            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle")
            actions_log.append("✅ Connexion effectuée")

            link = gm.confirm_latest_email()
            if link:
                print("confirmation OK:", link)
            else:
                print("pas de mail reçu")
            # --- Screenshot ---
            os.makedirs("screenshots", exist_ok=True)
            page.screenshot(path="screenshots/apres_login.png")
            actions_log.append("✅ Screenshot pris")

            # --- Découverte des onglets ---
            tabs = page.query_selector_all("nav a")
            for tab in tabs:
                tab_name = tab.inner_text().strip()
                if tab_name:
                    tab.click()
                    page.wait_for_load_state("networkidle")
                    page.screenshot(path=f"screenshots/onglet_{tab_name}.png")
                    actions_log.append(f"✅ Onglet visité : {tab_name}")

        except Exception as e:
            error_msg = f"❌ Erreur : {str(e)}"
            report["erreurs"].append(error_msg)
            page.screenshot(path="screenshots/erreur.png")

        finally:
            browser.close()

    report["actions"] = actions_log

    # Sauvegarde du rapport JSON
    os.makedirs("reports", exist_ok=True)
    report_path = f"reports/report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Affichage dans les logs GitHub Actions
    print("\n📋 RAPPORT D'EXÉCUTION :")
    for action in actions_log:
        print(action)
    if report["erreurs"]:
        print("\n⚠️ ERREURS :")
        for err in report["erreurs"]:
            print(err)

    return report

if __name__ == "__main__":
    run_bot()