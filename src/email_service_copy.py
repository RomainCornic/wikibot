import requests
import random
import string
import time
import re


class GuerrillaMailClient:
    API_URL = "https://api.guerrillamail.com/ajax.php"

    def __init__(self, prefix="user"):
        self.session = requests.Session()
        self.prefix = prefix
        self.email = None
        self.sid_token = None

    def create_email(self):
        suffix = ''.join(
            random.choices(string.ascii_lowercase + string.digits, k=8)
        )

        username = f"{self.prefix}_{suffix}"

        response = self.session.get(
            self.API_URL,
            params={
                "f": "set_email_user",
                "email_user": username
            }
        )

        data = response.json()

        self.email = data["email_addr"]
        self.sid_token = data.get("sid_token")

        return self.email

    def wait_for_email(self, timeout=60, poll_interval=3):
        start = time.time()

        while time.time() - start < timeout:
            response = self.session.get(
                self.API_URL,
                params={
                    "f": "check_email",
                    "seq": 0
                }
            )

            data = response.json()

            if data.get("list"):
                return data["list"][0]

            time.sleep(poll_interval)

        return None

    def fetch_email(self, mail_id):
        response = self.session.get(
            self.API_URL,
            params={
                "f": "fetch_email",
                "email_id": mail_id
            }
        )

        return response.json()

    @staticmethod
    def extract_link(text):
        match = re.search(r'https?://[^\s"\']+', text)
        return match.group(0) if match else None

    def confirm_latest_email(self, timeout=60):
        mail = self.wait_for_email(timeout=timeout)

        if not mail:
            return None

        content = self.fetch_email(mail["mail_id"])
        body = content.get("mail_body", "")

        link = self.extract_link(body)

        if link:
            self.session.get(link)

        return link
    
    def get_latest_code(self, timeout=60, pattern=r"\b\d{6}\b"):
        mail = self.wait_for_email(timeout=timeout)

        if not mail:
            return None

        content = self.fetch_email(mail["mail_id"])

        # certains mails mettent le code dans le body HTML, d'autres dans le texte
        body = (
            content.get("mail_body", "")
            or content.get("mail_excerpt", "")
        )

        match = re.search(pattern, body)

        if match:
            return match.group(0)

        return None