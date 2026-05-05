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

def load_bots_db() -> dict:
    if os.path.exists(BOTS_DB_PATH):
        with open(BOTS_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"bots": []}


def save_bots_db(db: dict):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(BOTS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# Navigation

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
    path = os.path.join(SCREENSHOTS_DIR, f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    page.screenshot(path=path)
    return path
