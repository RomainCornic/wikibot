import requests
import random
import string

def generate_temp_email():
    # Génère un nom aléatoire
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"testuser_{suffix}@guerrillamail.com"
    return email

def get_emails(email_address):
    # Récupère les emails reçus via l'API Guerrilla Mail
    username = email_address.split('@')[0]
    response = requests.get(
        f"https://api.guerrillamail.com/ajax.php",
        params={"f": "get_email_list", "offset": 0, "alias": username}
    )
    return response.json()