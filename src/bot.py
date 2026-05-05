from playwright.sync_api import sync_playwright,Page
import json
import os
from datetime import datetime
from random_username.generate import generate_username
from email_service_copy import GuerrillaMailClient
import re
import random




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
        known_ids = gm.snapshot_mail_ids()

        try:
            # --- Navigation ---
            page.goto(SITE_URL)
            actions_log.append("✅ Navigation vers la page de login")
            # --- Inscription/Connexion ---
            page.get_by_role("textbox", name="Nom d'utilisateur").fill(username)
            page.get_by_role("textbox", name="Adresse courriel").fill(email)
            page.get_by_role("textbox", name="Mot de passe").fill("TestPassword123!")

            page.fill("#username", username)
            page.get_by_role("checkbox", name="Je confirme avoir au moins 18").check()
            page.get_by_role("button", name="Créer mon compte").click()


            print("waiting for code")
            print("known IDs:",known_ids)
            mail = gm.wait_for_matching_email(known_ids=known_ids)
            print("mail:",mail)

            code = gm.get_latest_code(mail)


            assert code is not None, "Pas de mail recu ou pas de code trouvé"
                
            page.get_by_role("textbox", name="Code de vérification").fill(code)
            page.get_by_role("button", name="Vérifier et continuer").click()

            # page.wait_for_load_state("networkidle")
            actions_log.append("✅ Connexion effectuée")


            # --- Screenshot ---
            os.makedirs("screenshots", exist_ok=True)
            page.screenshot(path="screenshots/apres_login.png")
            actions_log.append("✅ Screenshot pris")
            page.get_by_role("link", name="Paquets").wait_for(state="visible",timeout=5000)
            page.get_by_role("link", name="Paquets").click()
            counter=get_counter_value(page)
            while counter>0:
                open_paquet(page)
                counter=get_counter_value(page)
                page.wait_for_timeout(100)

            
        except Exception as e:
            error_msg = f"❌ Erreur : {e}"
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


def open_paquet(page: Page):
    page.get_by_role("button", name="Ouvrir un paquet Ouvrir").click()
    page.locator(".flex.items-center.gap-4 > button:nth-child(3)").wait_for(state="visible",timeout=5000)
    page.locator(".flex.items-center.gap-4 > button:nth-child(3)").click()
    page.wait_for_timeout(random.randint(25,250))
    page.locator(".flex.items-center.gap-4 > button:nth-child(3)").click()
    page.wait_for_timeout(random.randint(25,250))
    page.locator(".flex.items-center.gap-4 > button:nth-child(3)").click()
    page.wait_for_timeout(random.randint(25,250))
    page.locator(".flex.items-center.gap-4 > button:nth-child(3)").click()
    page.wait_for_timeout(random.randint(25,250))
    page.get_by_role("button", name="Continuer").click()

def get_counter_value(page: Page):
    element = page.locator('span.text-\\[var\\(--color-accent\\)\\]')
    return int(element.inner_text().strip())

if __name__ == "__main__":
    run_bot()