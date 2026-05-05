"""
migrate.py — Convertit les anciens rapports JSON vers bots_db.json

Ancien format (report_*.json) :
  { "date": "...", "email_utilisé": "...", "actions": [...], "erreurs": [...] }

Nouveau format (bots_db.json) :
  { "bots": [{ "id", "username", "email", "password", "created_at", "sessions": [...] }] }

Usage :
  python migrate.py                         # scanne ./reports/ automatiquement
  python migrate.py --dir /chemin/rapports  # dossier personnalisé
  python migrate.py --file report_x.json    # fichier unique
  python migrate.py --dry-run               # aperçu sans écrire
"""

import json
import os
import re
import argparse
from datetime import datetime
from pathlib import Path


REPORTS_DIR  = "reports"
BOTS_DB_PATH = os.path.join(REPORTS_DIR, "bots_db.json")
DEFAULT_PASSWORD = "TestPassword123!"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_bots_db() -> dict:
    if os.path.exists(BOTS_DB_PATH):
        with open(BOTS_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"bots": []}


def save_bots_db(db: dict):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(BOTS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def is_old_format(data: dict) -> bool:
    """Détecte l'ancien format via la clé 'email_utilisé'."""
    return "email_utilisé" in data and "bots" not in data


def is_new_format(data: dict) -> bool:
    return "bots" in data


def extract_username_from_email(email: str) -> str:
    """Extrait la partie avant le _ ou @ pour deviner le username."""
    local = email.split("@")[0]          # ex: euphoricSeagull8_x9hwhtrm
    username = local.split("_")[0]       # ex: euphoricSeagull8
    return username or local


def parse_old_date(date_str: str) -> str:
    """Convertit '2026-05-05 22:24:40' → ISO 8601."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return dt.isoformat()
    except Exception:
        return datetime.now().isoformat()


def paquets_from_actions(actions: list) -> int:
    """Tente de lire le nombre de paquets depuis les actions loggées."""
    for action in actions:
        match = re.search(r"(\d+)\s+paquets?\s+ouverts?", action, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


def already_imported(db: dict, email: str) -> bool:
    return any(b.get("email") == email for b in db.get("bots", []))


# ─── Conversion ───────────────────────────────────────────────────────────────

def convert_old_report(data: dict, source_file: str = "") -> dict:
    """Convertit un ancien rapport en entrée bot au nouveau format."""
    email     = data.get("email_utilisé", "")
    date_raw  = data.get("date", "")
    actions   = data.get("actions", [])
    erreurs   = data.get("erreurs", [])

    date_iso  = parse_old_date(date_raw)
    username  = extract_username_from_email(email)
    bot_id    = datetime.fromisoformat(date_iso).strftime("%Y%m%d%H%M%S")

    session = {
        "date":           date_iso,
        "type":           "migrated",
        "source_file":    os.path.basename(source_file),
        "actions":        actions,
        "errors":         erreurs,
        "paquets_opened": paquets_from_actions(actions),
        "screenshots":    []
    }

    bot = {
        "id":         bot_id,
        "username":   username,
        "email":      email,
        "password":   DEFAULT_PASSWORD,
        "created_at": date_iso,
        "sessions":   [session]
    }

    return bot


# ─── File processing ──────────────────────────────────────────────────────────

def process_file(path: str, db: dict, dry_run: bool) -> tuple[int, int]:
    """
    Traite un fichier JSON.
    Retourne (imported, skipped).
    """
    imported = skipped = 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠️  Lecture impossible ({os.path.basename(path)}) : {e}")
        return 0, 0

    # Fichier au nouveau format avec plusieurs bots (bots_db)
    if is_new_format(data):
        for bot in data.get("bots", []):
            email = bot.get("email", "")
            if already_imported(db, email):
                print(f"  ⏭  Déjà présent : {email}")
                skipped += 1
            else:
                if not dry_run:
                    db["bots"].append(bot)
                print(f"  ✅ Importé (nouveau format) : {bot.get('username')} — {email}")
                imported += 1
        return imported, skipped

    # Ancien format (rapport individuel)
    if is_old_format(data):
        email = data.get("email_utilisé", "")
        if already_imported(db, email):
            print(f"  ⏭  Déjà présent : {email}")
            return 0, 1

        bot = convert_old_report(data, source_file=path)
        if not dry_run:
            db["bots"].append(bot)
        print(f"  ✅ Converti : {bot['username']} — {email}"
              f"  ({bot['sessions'][0]['paquets_opened']} paquets, "
              f"{len(bot['sessions'][0]['errors'])} erreur(s))")
        return 1, 0

    print(f"  ❓ Format non reconnu : {os.path.basename(path)}")
    return 0, 0


def scan_directory(directory: str, db: dict, dry_run: bool) -> tuple[int, int]:
    """Scanne un dossier et traite tous les JSON sauf bots_db.json."""
    total_imported = total_skipped = 0
    files = sorted(Path(directory).glob("*.json"))

    if not files:
        print(f"Aucun fichier JSON trouvé dans {directory}")
        return 0, 0

    for path in files:
        if path.name == "bots_db.json":
            continue  # ne pas importer la DB elle-même
        print(f"\n📄 {path.name}")
        imp, skip = process_file(str(path), db, dry_run)
        total_imported += imp
        total_skipped  += skip

    return total_imported, total_skipped


# ─── Main ─────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Migration anciens rapports → bots_db.json")
parser.add_argument("--dir",     type=str, default=REPORTS_DIR, help="Dossier à scanner")
parser.add_argument("--file",    type=str, help="Fichier unique à importer")
parser.add_argument("--dry-run", action="store_true", help="Aperçu sans écrire")
args = parser.parse_args()

print("=" * 55)
print("  Migration WikiMasters → bots_db.json")
if args.dry_run:
    print("  MODE DRY-RUN : aucune écriture")
print("=" * 55)

db = load_bots_db()
bots_before = len(db.get("bots", []))
print(f"\n📂 Base actuelle : {bots_before} bot(s)\n")

if args.file:
    print(f"📄 Fichier unique : {args.file}")
    imp, skip = process_file(args.file, db, args.dry_run)
else:
    print(f"📁 Scan de : {args.dir}")
    imp, skip = scan_directory(args.dir, db, args.dry_run)

# Sauvegarde
if not args.dry_run and imp > 0:
    save_bots_db(db)
    print(f"\n💾 bots_db.json mis à jour")

# Résumé
print(f"\n{'─' * 55}")
print(f"  Importés  : {imp}")
print(f"  Ignorés   : {skip} (déjà présents)")
print(f"  Total DB  : {len(db.get('bots', []))} bot(s)")
print(f"{'─' * 55}\n")

if args.dry_run:
    print("ℹ️  Dry-run terminé — relance sans --dry-run pour appliquer")

