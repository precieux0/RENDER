"""
gmail_api.py - Remplacement de smtp_pool.py utilisant l'API Gmail (HTTPS/443).

Fonctionne sur Render (où les ports SMTP 465/587 sont bloqués) car tout
passe par HTTPS. Conserve les mêmes méthodes que SMTPPool/bot.py:

    pool = GmailAPIPool(accounts)
    ok, err = pool.send_email(account, to, subject, body, sender_name)
    ok, err = pool.send_simple(to, subject, body)            # API simple
    s, f, details = pool.send_multiple(to, subject, body, count)
    results = pool.test_all()                                # /test_smtp

Format d'un compte (un par Gmail):
    {
      "email": "user@gmail.com",
      "client_id":     "xxx.apps.googleusercontent.com",
      "client_secret": "GOCSPX-xxx",
      "refresh_token": "1//0gxxx"
    }

Le client_id / client_secret peuvent être communs à plusieurs comptes
(une seule app Google Cloud), seul le refresh_token est par compte.
"""

import base64
import time
import random
import threading
from email.message import EmailMessage
from email.utils import formataddr

import requests

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class GmailAccount:
    """Encapsule un compte Gmail + cache d'access_token."""

    def __init__(self, email, client_id, client_secret, refresh_token):
        self.email = email
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._access_token = None
        self._expires_at = 0
        self._lock = threading.Lock()
        self.failures = 0

    def get_access_token(self, force=False):
        """Rafraîchit l'access_token si nécessaire (cache 50 min)."""
        with self._lock:
            now = time.time()
            if not force and self._access_token and now < self._expires_at - 60:
                return self._access_token
            resp = requests.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=20,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Refresh token failed for {self.email}: "
                    f"{resp.status_code} {resp.text}"
                )
            data = resp.json()
            self._access_token = data["access_token"]
            self._expires_at = now + int(data.get("expires_in", 3600))
            return self._access_token


class GmailAPIPool:
    def __init__(self, accounts):
        """
        `accounts` : liste de dicts. Chaque dict doit contenir au minimum
        email + (client_id, client_secret, refresh_token).
        Les comptes mal configurés sont ignorés avec un warning.
        """
        self.accounts = []
        for acc in accounts:
            try:
                self.accounts.append(GmailAccount(
                    email=acc["email"],
                    client_id=acc["client_id"],
                    client_secret=acc["client_secret"],
                    refresh_token=acc["refresh_token"],
                ))
            except KeyError as e:
                print(f"⚠️  Compte ignoré (champ manquant {e}): {acc.get('email')}")
        self.invalid = set()  # emails temporairement KO

    # ------------------------------------------------------------------
    # Sélection / rotation
    # ------------------------------------------------------------------
    def _pick(self, exclude_email=None):
        candidates = [
            a for a in self.accounts
            if a.email not in self.invalid and a.email != exclude_email
            and a.failures < 3
        ]
        if not candidates:
            candidates = [a for a in self.accounts if a.email != exclude_email]
        if not candidates:
            return None
        return random.choice(candidates)

    def get_account_by_email(self, email):
        for a in self.accounts:
            if a.email == email:
                return a
        return None

    # ------------------------------------------------------------------
    # Envoi bas niveau
    # ------------------------------------------------------------------
    @staticmethod
    def _build_raw(from_email, to, subject, body, sender_name=None):
        msg = EmailMessage()
        msg.set_content(body, charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr((sender_name or "", from_email))
        msg["To"] = to
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        return raw

    def _send_with_account(self, account, to, subject, body, sender_name=None):
        try:
            token = account.get_access_token()
        except Exception as e:
            account.failures += 1
            self.invalid.add(account.email)
            return False, f"OAuth: {e}"

        raw = self._build_raw(account.email, to, subject, body, sender_name)
        try:
            resp = requests.post(
                GMAIL_SEND_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"raw": raw},
                timeout=30,
            )
        except Exception as e:
            account.failures += 1
            return False, f"HTTP: {e}"

        if resp.status_code == 200:
            account.failures = 0
            print(f"✅ Gmail API: envoyé via {account.email} -> {to}")
            return True, None

        # 401 => token invalidé : on retente une fois après refresh forcé
        if resp.status_code == 401:
            try:
                token = account.get_access_token(force=True)
                resp = requests.post(
                    GMAIL_SEND_URL,
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"},
                    json={"raw": raw}, timeout=30,
                )
                if resp.status_code == 200:
                    account.failures = 0
                    return True, None
            except Exception as e:
                account.failures += 1
                self.invalid.add(account.email)
                return False, f"OAuth refresh: {e}"

        account.failures += 1
        if resp.status_code in (401, 403):
            self.invalid.add(account.email)

        err = f"Gmail API {resp.status_code}: {resp.text[:300]}"
        print(f"❌ {account.email}: {err}")
        return False, err

    # ------------------------------------------------------------------
    # API publique (compatible bot.py existant)
    # ------------------------------------------------------------------
    def send_email(self, account, to, subject, body, sender_name=None):
        """
        Compatible avec l'appel bot.py:
            send_email(account_dict_or_obj, to, subject, body, sender_name)
        Le 1er paramètre peut être un dict {"email": ...} ou un GmailAccount.
        """
        acc_obj = account
        if isinstance(account, dict):
            acc_obj = self.get_account_by_email(account.get("email"))
            if acc_obj is None:
                return False, f"Compte {account.get('email')} introuvable dans le pool"
        return self._send_with_account(acc_obj, to, subject, body, sender_name)

    def send_simple(self, to, subject, body, sender_name=None):
        """API style smtp_pool.SMTPPool.send_email(to, subject, body)."""
        acc = self._pick()
        if not acc:
            return False, "Aucun compte Gmail disponible"
        return self._send_with_account(acc, to, subject, body, sender_name)

    def send_with_retry(self, to, subject, body, sender_name=None, max_retries=2):
        last_err = "Aucun compte"
        used = None
        for attempt in range(max_retries):
            acc = self._pick(exclude_email=used)
            if not acc:
                return False, last_err
            used = acc.email
            ok, err = self._send_with_account(acc, to, subject, body, sender_name)
            if ok:
                return True, None
            last_err = err
            time.sleep(1)
        return False, f"Échec après {max_retries} tentatives: {last_err}"

    def send_multiple(self, to, subject, body, count, delay=2.0, sender_name=None):
        success, fail, details = 0, 0, []
        for i in range(count):
            ok, err = self.send_with_retry(
                to, f"{subject} #{i+1}", body + f"\n\n--- Rapport {i+1} ---",
                sender_name=sender_name,
            )
            if ok:
                success += 1
            else:
                fail += 1
            details.append({"index": i + 1, "success": ok, "error": err})
            if i < count - 1:
                time.sleep(delay)
        return success, fail, details

    # ------------------------------------------------------------------
    # Diagnostic /test_smtp
    # ------------------------------------------------------------------
    def test_all(self):
        """Teste chaque compte (refresh token + appel léger Gmail).
        Retourne [{email, ok, error}]."""
        results = []
        for acc in self.accounts:
            entry = {"email": acc.email, "ok": False, "error": None}
            try:
                token = acc.get_access_token(force=True)
                # Appel "profile" très léger pour valider le scope gmail.send
                r = requests.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15,
                )
                if r.status_code == 200:
                    entry["ok"] = True
                    self.invalid.discard(acc.email)
                    acc.failures = 0
                else:
                    entry["error"] = f"{r.status_code} {r.text[:200]}"
            except Exception as e:
                entry["error"] = str(e)
            results.append(entry)
        return results
