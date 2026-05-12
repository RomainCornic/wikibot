import random
import re
import string
import time

import requests


class GuerrillaMailClient:
    API_URL = "https://api.guerrillamail.com/ajax.php"

    def __init__(self, prefix="user"):
        self.session = requests.Session()
        self.prefix = prefix
        self.email = None
        self.sid_token = None

    def create_email(self):
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))

        username = f"{self.prefix}_{suffix}"

        response = self.session.get(
            self.API_URL, params={"f": "set_email_user", "email_user": username}
        )

        data = response.json()

        self.email = data["email_addr"]
        self.sid_token = data.get("sid_token")

        return self.email

    def wait_for_email(self, timeout=60, poll_interval=3):
        start = time.time()

        while time.time() - start < timeout:
            response = self.session.get(
                self.API_URL, params={"f": "check_email", "seq": 0}
            )

            data = response.json()

            if data.get("list"):
                return data["list"][0]

            time.sleep(poll_interval)

        return None

    def fetch_email(self, mail_id):
        response = self.session.get(
            self.API_URL, params={"f": "fetch_email", "email_id": mail_id}
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

    def get_latest_code(self, mail, pattern=r"\b\d{6}\b"):
        content = self.fetch_email(mail["mail_id"])

        body = content.get("mail_body", "") or content.get("mail_excerpt", "")

        match = re.search(r"\b(\d{6})\b", body)

        if match:
            return match.group(1)

        return None

    def snapshot_mail_ids(self):
        mails = self.get_email_list()
        return {mail["mail_id"] for mail in mails}

    def wait_for_matching_email(
        self,
        known_ids=None,
        sender=None,
        subject_contains=None,
        timeout=60,
        poll_interval=3,
    ):
        known_ids = known_ids or set()

        start = time.time()

        while time.time() - start < timeout:
            mails = self.get_email_list()
            for mail in mails:
                mail_id = mail["mail_id"]

                if mail_id in known_ids:
                    continue

                mail_sender = mail.get("mail_from", "").lower()
                mail_subject = mail.get("mail_subject", "").lower()

                if sender and sender.lower() not in mail_sender:
                    continue

                if subject_contains and subject_contains.lower() not in mail_subject:
                    continue

                return mail

            time.sleep(poll_interval)

        return None

    def get_email_list(self):
        response = self.session.get(
            self.API_URL, params={"f": "get_email_list", "offset": 0}
        )

        data = response.json()
        return data.get("list", [])
