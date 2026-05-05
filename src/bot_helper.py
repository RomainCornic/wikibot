from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
import json
import os
import random
from datetime import datetime


# Config

SITE_URL     = os.environ.get("SITE_URL", "https://www.wiki-masters.com/")
LOGIN_URL    = SITE_URL + "login"
HEADLESS     = os.environ.get("HEADLESS", "true").lower() == "true"
REPORTS_DIR  = "reports"
SCREENSHOTS_DIR = "screenshots"
BOTS_DB_PATH = os.path.join(REPORTS_DIR, "bots_db.json")
# DB


def screenshot(page: Page, name: str):
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOTS_DIR, f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    page.screenshot(path=path)
    return path

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

# Navigation

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
