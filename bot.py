#!/usr/bin/env python3
"""
WhatsApp Reporter Bot — 100% Gmail API (HTTPS), compatible Render.
"""

import requests
import time
import random
import json
import os
import threading
import sys
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict

from gmail_api import GmailAPIPool

# ================= CONFIGURATION =================
ADMIN_ID = int(os.getenv("ADMIN_ID", "7684684739"))
CHANNEL_USERNAME = "@wabanreport"
CHANNEL_LINK = "https://t.me/+tmrGH8UwjUw4ODY0"
PORT = int(os.environ.get("PORT", 8080))

# Token Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("ERREUR: TELEGRAM_TOKEN non défini")
    sys.exit(1)

# Paramètres d’envoi
EMAIL_DELAY = float(os.getenv("EMAIL_DELAY", "2.0"))
MAX_REPORTS_PER_HOUR = int(os.getenv("MAX_REPORTS_PER_HOUR", 100))
MIN_REPORTS = int(os.getenv("MIN_REPORTS", "10"))
MAX_REPORTS = int(os.getenv("MAX_REPORTS", "50"))

# ================= GESTION DES COMPTES =================
def load_accounts():
    """Charge les comptes depuis la variable d'environnement SMTP_ACCOUNTS."""
    accounts = []
    env_accounts = os.getenv("SMTP_ACCOUNTS", "[]")
    try:
        parsed = json.loads(env_accounts)
        if isinstance(parsed, list):
            accounts.extend(parsed)
            print(f"✅ {len(parsed)} compte(s) chargés depuis SMTP_ACCOUNTS (env)")
    except json.JSONDecodeError:
        print("⚠️ SMTP_ACCOUNTS dans l'environnement n'est pas un JSON valide")

    # Déduplication par email
    seen = set()
    unique = []
    for acc in accounts:
        email = acc.get("email")
        if email and email not in seen:
            seen.add(email)
            unique.append(acc)
    return unique

SMTP_ACCOUNTS = load_accounts()

# Destinataires
def load_recipients():
    env_recipients = os.getenv("WHATSAPP_RECIPIENTS", '["support@support.whatsapp.com","abuse@whatsapp.com"]')
    try:
        parsed = json.loads(env_recipients)
        if isinstance(parsed, list):
            print(f"✅ Destinataires chargés: {len(parsed)}")
            return parsed
    except json.JSONDecodeError:
        print("⚠️ WHATSAPP_RECIPIENTS invalide")
    return ["support@support.whatsapp.com", "abuse@whatsapp.com"]

WHATSAPP_RECIPIENTS = load_recipients()

# ================= ÉTAT GLOBAL =================
user_sessions = {}
user_stats = defaultdict(lambda: {"count": 0, "last_reset": time.time()})
invalid_smtp = set()  # utilisé pour compatibilité

# Pool Gmail API
gmail_pool = GmailAPIPool(SMTP_ACCOUNTS)
print(f"📨 Gmail API : {len(gmail_pool.accounts)} compte(s) prêt(s)")

def rebuild_pool():
    global gmail_pool
    gmail_pool = GmailAPIPool(SMTP_ACCOUNTS)

def test_smtp_connection():
    """Teste tous les comptes via l'API Gmail (appelé au démarrage)."""
    if not gmail_pool.accounts:
        print("⚠️ Aucun compte Gmail configuré")
        return []
    print("🔍 Test API Gmail pour chaque compte...")
    results = gmail_pool.test_all()
    for r in results:
        if r["ok"]:
            print(f"  ✅ {r['email']}")
        else:
            print(f"  ❌ {r['email']} -> {r['error']}")
    return results

# ================= ENVOI D'EMAIL (via API Gmail) =================
def send_email(account, to, subject, body, sender_name):
    """Enveloppe pour compatibilité avec l'ancien code."""
    ok, err = gmail_pool.send_email(account, to, subject, body, sender_name)
    if not ok and account.get("email"):
        invalid_smtp.add(account["email"])
    elif ok:
        invalid_smtp.discard(account["email"])
    return ok, err

def send_with_retry(account, to, subject, body, sender_name, max_retries=2):
    """Tente l'envoi avec rotation entre comptes."""
    err = "Aucun compte disponible"
    for attempt in range(max_retries):
        if attempt > 0:
            available = [a for a in SMTP_ACCOUNTS
                         if a["email"] != account["email"]
                         and a["email"] not in invalid_smtp]
            if not available:
                return False, "Aucun compte Gmail alternatif disponible"
            account = random.choice(available)
            print(f"🔄 Nouvelle tentative avec {account['email']}")
        ok, err = send_email(account, to, subject, body, sender_name)
        if ok:
            return True, None
        time.sleep(1)
    return False, f"Échec après {max_retries} tentatives: {err}"

# ================= GÉNÉRATION DE RAPPORTS =================
FIRST_NAMES = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
               "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
               "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
               "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
               "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Kenneth", "Michelle",
               "Joshua", "Dorothy", "George", "Carol", "Kevin", "Amanda", "Brian", "Melissa",
               "Edward", "Deborah", "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason", "Sharon",
               "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
               "Nicholas", "Shirley", "Eric", "Angela", "Jonathan", "Helen", "Stephen", "Anna",
               "Larry", "Brenda", "Justin", "Pamela", "Scott", "Nicole", "Brandon", "Emma",
               "Benjamin", "Samantha", "Samuel", "Katherine", "Gregory", "Christine", "Alexander",
               "Debra", "Frank", "Rachel", "Patrick", "Catherine", "Raymond", "Carolyn", "Jack",
               "Janet", "Dennis", "Ruth", "Jerry", "Maria", "Tyler", "Heather", "Aaron", "Diane",
               "Jose", "Virginia", "Adam", "Julie"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
              "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
              "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
              "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
              "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
              "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
              "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
              "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy",
              "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey",
              "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson", "Watson",
              "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz",
              "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long",
              "Ross", "Foster", "Jimenez"]

def random_sender_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def generate_detailed_report(number, category, report_index=1):
    incidents = [
        {"title": "Spam and Phishing", "desc": f"Unsolicited messages from {number} promoting fake investments with phishing links.", "evidence": "Screenshots attached.", "action": "Permanently ban this number."},
        {"title": "Harassment and Threats", "desc": f"Since {datetime.now().strftime('%B %d')}, {number} has been sending abusive messages including death threats.", "evidence": "Chat logs available.", "action": "Suspend account and preserve logs."},
        {"title": "Impersonation and Fraud", "desc": f"The account {number} is impersonating my colleague using stolen photos, asking for money.", "evidence": "Screenshots of fake profile.", "action": "Block the account immediately."},
        {"title": "Illegal Content", "desc": f"{number} is sharing explicit adult content in a group that includes minors.", "evidence": "Screenshots of messages.", "action": "Remove the account."},
        {"title": "Privacy Violation", "desc": f"The user posted my private phone number on a public WhatsApp group without consent.", "evidence": "Screenshots available.", "action": "Remove the content."},
    ]
    incident = random.choice(incidents)
    return f"""URGENT: WhatsApp Terms of Service Violation - {incident['title']}

Number: {number}
Category: {category}
Report ID: RPT-{random.randint(10000,99999)}-{report_index}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Description:
{incident['desc']}

Evidence:
{incident['evidence']}

Action requested:
{incident['action']}

Sincerely,
[Concerned User]"""

def generate_subject(number, category):
    return random.choice([
        f"Violation - {number} ({category})",
        f"Complaint: {category} from {number}",
        f"URGENT: {category} - {number}",
    ])

# ================= FONCTIONS TELEGRAM =================
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erreur send_message: {e}")

def edit_message(chat_id, msg_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
    try:
        requests.post(url, json={"chat_id": chat_id, "message_id": msg_id, "text": text}, timeout=10)
    except Exception as e:
        print(f"Erreur edit_message: {e}")

def answer_callback(callback_id):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                  json={"callback_query_id": callback_id})

def send_message_and_get_id(chat_id, text):
    resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                         json={"chat_id": chat_id, "text": text}, timeout=10).json()
    return resp.get("result") if resp.get("ok") else None

def is_valid_number(num):
    return num.startswith("+") and num[1:].replace(" ", "").isdigit() and len(num) >= 8

def is_admin(user_id):
    return user_id == ADMIN_ID

# ================= VÉRIFICATION MEMBRE =================
def check_membership(user_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember"
    params = {"chat_id": CHANNEL_USERNAME, "user_id": user_id}
    try:
        resp = requests.get(url, params=params, timeout=10).json()
        if resp.get("ok"):
            status = resp["result"].get("status")
            return status in ("member", "administrator", "creator")
        return False
    except Exception as e:
        print(f"Erreur check_membership: {e}")
        return False

def is_member(user_id):
    return check_membership(user_id)

def send_join_required(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "📢 Rejoindre le canal", "url": CHANNEL_LINK}],
            [{"text": "✅ J'ai rejoint", "callback_data": "verify_join"}],
        ]
    }
    send_message(chat_id,
        "🚨 *Accès restreint*\n\n"
        "Pour utiliser ce bot, vous devez d'abord rejoindre notre canal.\n\n"
        f"👥 Canal: {CHANNEL_USERNAME}\n\n"
        "Rejoignez et cliquez sur *'J'ai rejoint'* pour continuer.\n\n"
        "👤 Dev: @bestiemondie426",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

# ================= GESTION DES SESSIONS =================
SESSION_TIMEOUT = 300  # 5 minutes

def clean_sessions():
    now = time.time()
    expired = [uid for uid, s in user_sessions.items() if now - s.get("timestamp", 0) > SESSION_TIMEOUT]
    for uid in expired:
        del user_sessions[uid]
        print(f"Session expirée pour {uid}")

def check_rate_limit(user_id):
    now = time.time()
    stats = user_stats[user_id]
    if now - stats["last_reset"] > 3600:
        stats["count"] = 0
        stats["last_reset"] = now
    return stats["count"] < MAX_REPORTS_PER_HOUR

def update_rate_limit(user_id, delta):
    stats = user_stats[user_id]
    stats["count"] += delta

# ================= COMMANDES =================
def handle_command(chat_id, user_id, cmd):
    if cmd not in ("/start", "/admin", "/help", "/test_smtp"):
        if not is_member(user_id):
            send_join_required(chat_id)
            return

    if cmd == "/start":
        user_sessions.pop(user_id, None)
        if is_member(user_id):
            msg = (
                "🚀 *WhatsApp Reporter Bot*\n\n"
                "/report - Signalement manuel (1-10)\n"
                "/autoreport - Signalement automatique (10-50)\n"
                "/stats - Votre quota horaire\n"
                "/help - Aide et informations"
            )
            send_message(chat_id, msg, parse_mode="Markdown")
        else:
            send_join_required(chat_id)

    elif cmd == "/help":
        send_message(chat_id,
            "🤖 Ce bot vous aide à signaler des numéros WhatsApp abusifs.\n\n"
            "Commandes:\n"
            "/report - Lancer un signalement avec choix de catégorie (1-10)\n"
            "/autoreport - Signalement automatique (vous choisissez la quantité entre 10 et 50)\n"
            "/stats - Voir votre quota de rapports restant cette heure\n\n"
            "Pour toute question, contactez @bestiemondie426"
        )

    elif cmd == "/stats":
        if not is_member(user_id):
            send_join_required(chat_id)
            return
        stats = user_stats[user_id]
        remaining = max(0, MAX_REPORTS_PER_HOUR - stats["count"])
        send_message(chat_id, f"📊 Votre activité:\n\nRapports envoyés cette heure: {stats['count']}\nRapports restants: {remaining}")

    elif cmd == "/admin":
        if is_admin(user_id):
            admin_panel(chat_id)
        else:
            send_message(chat_id, "⛔ Accès refusé.")

    elif cmd == "/test_smtp":
        if not is_admin(user_id):
            send_message(chat_id, "⛔ Accès refusé.")
            return
        admin_test_smtp(chat_id)

    elif cmd == "/report":
        if not is_member(user_id):
            send_join_required(chat_id)
            return
        if not check_rate_limit(user_id):
            send_message(chat_id, "⏰ Limite horaire atteinte. Réessayez plus tard.")
            return
        user_sessions[user_id] = {"step": "report_number", "data": {}, "timestamp": time.time()}
        send_message(chat_id, "📱 Envoyez le numéro WhatsApp avec indicatif: +243812345678")

    elif cmd == "/autoreport":
        if not is_member(user_id):
            send_join_required(chat_id)
            return
        if not check_rate_limit(user_id):
            send_message(chat_id, "⏰ Limite horaire atteinte.")
            return
        user_sessions[user_id] = {"step": "autoreport_number", "data": {}, "timestamp": time.time()}
        send_message(chat_id, "📱 Envoyez le numéro WhatsApp avec indicatif:")

def admin_panel(chat_id):
    keyboard = {"inline_keyboard": [
        [{"text": "➕ Ajouter Gmail (JSON)", "callback_data": "admin_add_smtp"}],
        [{"text": "➖ Supprimer Gmail", "callback_data": "admin_del_smtp"}],
        [{"text": "📋 Lister Gmail", "callback_data": "admin_list_smtp"}],
        [{"text": "🧪 Test Gmail API", "callback_data": "admin_test_smtp"}],
        [{"text": "📨 Ajouter destinataire", "callback_data": "admin_add_recipient"}],
        [{"text": "🗑 Supprimer destinataire", "callback_data": "admin_del_recipient"}],
        [{"text": "📋 Lister destinataires", "callback_data": "admin_list_recipients"}],
        [{"text": "📊 Stats", "callback_data": "admin_stats"}],
    ]}
    send_message(chat_id, "🔧 Panneau d'administration", reply_markup=keyboard)

# ================= HANDLERS ADMIN =================
def add_smtp_account_json(chat_id, raw_json):
    global SMTP_ACCOUNTS
    try:
        acc = json.loads(raw_json)
    except Exception as e:
        send_message(chat_id, f"❌ JSON invalide: {e}")
        return
    needed = {"email", "client_id", "client_secret", "refresh_token"}
    missing = needed - set(acc.keys())
    if missing:
        send_message(chat_id, f"❌ Champs manquants: {', '.join(missing)}")
        return
    if any(a["email"] == acc["email"] for a in SMTP_ACCOUNTS):
        send_message(chat_id, f"❌ {acc['email']} existe déjà.")
        return
    SMTP_ACCOUNTS.append(acc)
    rebuild_pool()
    send_message(chat_id, f"✅ Compte Gmail ajouté: {acc['email']} — test en cours…")
    target = gmail_pool.get_account_by_email(acc["email"])
    try:
        target.get_access_token(force=True)
        send_message(chat_id, f"✅ OAuth OK pour {acc['email']}")
    except Exception as e:
        send_message(chat_id, f"⚠️ Ajouté mais OAuth échoué: {e}")

def add_smtp_account(chat_id, *args, **kwargs):
    send_message(chat_id, "ℹ️ Le bot utilise maintenant l'API Gmail. "
                          "Envoie un JSON {email,client_id,client_secret,refresh_token}.")

def remove_smtp_account(chat_id, email):
    global SMTP_ACCOUNTS
    SMTP_ACCOUNTS = [acc for acc in SMTP_ACCOUNTS if acc["email"] != email]
    rebuild_pool()
    send_message(chat_id, f"🗑 Compte Gmail supprimé: {email}")

def admin_test_smtp(chat_id):
    if not gmail_pool.accounts:
        send_message(chat_id, "Aucun compte Gmail configuré.")
        return
    send_message(chat_id, f"🧪 Test de {len(gmail_pool.accounts)} compte(s)…")
    results = gmail_pool.test_all()
    ok = sum(1 for r in results if r["ok"])
    lines = [f"📋 Résultat ({ok}/{len(results)} OK):"]
    for r in results:
        if r["ok"]:
            lines.append(f"✅ {r['email']}")
        else:
            lines.append(f"❌ {r['email']} — {r['error'][:120]}")
    send_message(chat_id, "\n".join(lines))

def list_smtp_accounts(chat_id):
    if not SMTP_ACCOUNTS:
        send_message(chat_id, "Aucun compte Gmail.")
        return
    msg = "📧 Comptes Gmail (API):\n"
    for i, acc in enumerate(SMTP_ACCOUNTS, 1):
        msg += f"{i}. {acc['email']}\n"
    send_message(chat_id, msg)

def add_recipient(chat_id, email):
    global WHATSAPP_RECIPIENTS
    if email not in WHATSAPP_RECIPIENTS:
        WHATSAPP_RECIPIENTS.append(email)
        send_message(chat_id, f"✅ Destinataire ajouté: {email}")
    else:
        send_message(chat_id, "❌ Existe déjà.")

def remove_recipient(chat_id, email):
    global WHATSAPP_RECIPIENTS
    if email in WHATSAPP_RECIPIENTS:
        WHATSAPP_RECIPIENTS.remove(email)
        send_message(chat_id, f"🗑 Destinataire supprimé: {email}")
    else:
        send_message(chat_id, "❌ Non trouvé.")

def list_recipients(chat_id):
    if not WHATSAPP_RECIPIENTS:
        send_message(chat_id, "Aucun destinataire.")
        return
    msg = "📨 Destinataires WhatsApp:\n"
    for i, rec in enumerate(WHATSAPP_RECIPIENTS, 1):
        msg += f"{i}. {rec}\n"
    send_message(chat_id, msg)

def admin_stats(chat_id):
    msg = (f"📊 Statistiques:\n\n"
           f"Comptes Gmail (API): {len(SMTP_ACCOUNTS)}\n"
           f"Pool actif: {len(gmail_pool.accounts)}\n"
           f"Comptes KO: {len(gmail_pool.invalid)}\n"
           f"Destinataires: {len(WHATSAPP_RECIPIENTS)}\n"
           f"Limite rapports/heure: {MAX_REPORTS_PER_HOUR}\n"
           f"Transport: Gmail API HTTPS\n"
           f"Intervalle email: {EMAIL_DELAY}s\n"
           f"Plage auto-report: {MIN_REPORTS}-{MAX_REPORTS}")
    send_message(chat_id, msg)

# ================= TRAITEMENT DES MESSAGES =================
def handle_text(chat_id, user_id, text):
    session = user_sessions.get(user_id)
    if not session:
        if text.startswith("/"):
            handle_command(chat_id, user_id, text.split()[0].lower())
        else:
            send_message(chat_id, "Utilisez /start pour commencer")
        return

    session["timestamp"] = time.time()
    step, data = session["step"], session["data"]

    # /report - étape 1 : numéro
    if step == "report_number" and is_valid_number(text):
        data["number"] = text
        session["step"] = "report_category"
        cats = ["Spam", "Harassment", "Fake Account", "Impersonation", "Illegal Activities",
                "Privacy Violation", "Threats", "Scam", "Abusive Content", "Other"]
        keyboard = {"inline_keyboard": [[{"text": c, "callback_data": f"cat_{i}"}] for i, c in enumerate(cats)]}
        send_message(chat_id, "📂 Choisissez la catégorie:", reply_markup=keyboard)

    # /autoreport - étape 1 : numéro
    elif step == "autoreport_number" and is_valid_number(text):
        data["number"] = text
        session["step"] = "autoreport_quantity"
        send_message(chat_id, f"Numéro: {text}\nCombien de rapports ? ({MIN_REPORTS}-{MAX_REPORTS})")

    # /autoreport - étape 2 : quantité
    elif step == "autoreport_quantity":
        try:
            qty = int(text)
            if MIN_REPORTS <= qty <= MAX_REPORTS:
                # catégorie aléatoire
                cats = ["Spam", "Harassment", "Fake Account", "Impersonation", "Illegal Activities",
                        "Privacy Violation", "Threats", "Scam", "Abusive Content", "Other"]
                category = random.choice(cats)
                data["category"] = category
                recipient = random.choice(WHATSAPP_RECIPIENTS)
                msg = send_message_and_get_id(chat_id, f"📧 Envoi de {qty} rapport(s)...")
                if msg:
                    send_multiple_reports(chat_id, msg["message_id"], data["number"], category, qty, recipient)
                    update_rate_limit(user_id, qty)
                del user_sessions[user_id]
            else:
                send_message(chat_id, f"❌ Choisissez un nombre entre {MIN_REPORTS} et {MAX_REPORTS}.")
        except ValueError:
            send_message(chat_id, "❌ Nombre invalide.")

    # /report - étape 3 : quantité (après avoir choisi la catégorie via callback)
    elif step == "report_quantity":
        try:
            qty = int(text)
            if 1 <= qty <= 10:   # plage manuelle plus restreinte
                recipient = random.choice(WHATSAPP_RECIPIENTS)
                msg = send_message_and_get_id(chat_id, f"📧 Envoi de {qty} rapport(s)...")
                if msg:
                    send_multiple_reports(chat_id, msg["message_id"], data["number"], data["category"], qty, recipient)
                    update_rate_limit(user_id, qty)
                del user_sessions[user_id]
            else:
                send_message(chat_id, "❌ Entrez un nombre entre 1 et 10.")
        except ValueError:
            send_message(chat_id, "❌ Entrez un nombre valide.")

    # Admin - ajout de compte Gmail (JSON)
    elif step == "admin_add_smtp":
        add_smtp_account_json(chat_id, text)
        del user_sessions[user_id]

    # Admin - ajout de destinataire
    elif step == "admin_add_recipient":
        add_recipient(chat_id, text)
        del user_sessions[user_id]

# ================= ENVOI DES RAPPORTS =================
def send_single_report(chat_id, msg_id, number, category, recipient):
    if not SMTP_ACCOUNTS:
        edit_message(chat_id, msg_id, "❌ Aucun compte configuré.")
        return
    available = [a for a in SMTP_ACCOUNTS if a["email"] not in invalid_smtp]
    if not available:
        edit_message(chat_id, msg_id, "❌ Tous les comptes sont temporairement inutilisables.")
        return
    account = random.choice(available)
    sender = random_sender_name()
    ok, err = send_with_retry(account, recipient, generate_subject(number, category),
                              generate_detailed_report(number, category), sender)
    if ok:
        edit_message(chat_id, msg_id, "✅ Envoi réussi !")
    else:
        edit_message(chat_id, msg_id, f"❌ Échec: {err}")

def send_multiple_reports(chat_id, msg_id, number, category, quantity, recipient):
    if not SMTP_ACCOUNTS:
        edit_message(chat_id, msg_id, "❌ Aucun compte configuré.")
        return
    success, fail = 0, 0
    available = [a for a in SMTP_ACCOUNTS if a["email"] not in invalid_smtp]
    if not available:
        edit_message(chat_id, msg_id, "❌ Tous les comptes sont temporairement inutilisables.")
        return
    for i in range(quantity):
        available = [a for a in SMTP_ACCOUNTS if a["email"] not in invalid_smtp]
        if not available:
            edit_message(chat_id, msg_id, "❌ Plus de comptes disponibles.")
            break
        account = random.choice(available)
        sender = random_sender_name()
        ok, err = send_with_retry(account, recipient,
                                  generate_subject(number, category),
                                  generate_detailed_report(number, category, i + 1),
                                  sender)
        if ok:
            success += 1
        else:
            fail += 1
            send_message(ADMIN_ID, f"⚠️ Échec rapport {i+1}/{quantity}: {err}")
        edit_message(chat_id, msg_id, f"📤 Progression: {i+1}/{quantity} | ✅ {success} | ❌ {fail}")
        time.sleep(EMAIL_DELAY)
    final = f"✅ Envoi terminé !\n\n📊 Rapports: {quantity}\n✅ Succès: {success}\n❌ Échecs: {fail}"
    edit_message(chat_id, msg_id, final)

# ================= CALLBACKS =================
def handle_callback(callback):
    user_id = callback["from"]["id"]
    chat_id = callback["message"]["chat"]["id"]
    msg_id = callback["message"]["message_id"]
    data = callback["data"]
    answer_callback(callback["id"])

    if data == "verify_join":
        if is_member(user_id):
            edit_message(chat_id, msg_id, "✅ Vérification réussie ! Vous pouvez maintenant utiliser le bot.")
        else:
            edit_message(chat_id, msg_id, f"❌ Vous n'avez pas encore rejoint {CHANNEL_USERNAME}. Rejoignez puis réessayez.")
        return

    if not data.startswith(("admin_", "del_", "delrec_", "cat_")):
        return

    # Catégories
    if data.startswith("cat_"):
        session = user_sessions.get(user_id)
        if session:
            idx = int(data.split("_")[1])
            cats = ["Spam", "Harassment", "Fake Account", "Impersonation", "Illegal Activities",
                    "Privacy Violation", "Threats", "Scam", "Abusive Content", "Other"]
            session["data"]["category"] = cats[idx]
            session["step"] = "report_quantity"
            edit_message(chat_id, msg_id, f"Catégorie: {cats[idx]}\n\nQuantité (1-10):")
        return

    # Admin
    if not is_admin(user_id):
        answer_callback(callback["id"], text="Accès refusé", show_alert=True)
        return

    if data == "admin_add_smtp":
        user_sessions[user_id] = {"step": "admin_add_smtp", "data": {}, "timestamp": time.time()}
        edit_message(chat_id, msg_id,
            "📧 Envoyez le compte Gmail au format JSON sur UNE ligne :\n"
            '{"email":"x@gmail.com","client_id":"…","client_secret":"…","refresh_token":"…"}')
    elif data == "admin_test_smtp":
        admin_test_smtp(chat_id)
    elif data == "admin_del_smtp":
        if not SMTP_ACCOUNTS:
            edit_message(chat_id, msg_id, "Aucun compte.")
            return
        env_accounts = json.loads(os.getenv("SMTP_ACCOUNTS", "[]"))
        env_emails = {acc["email"] for acc in env_accounts}
        editable = [acc for acc in SMTP_ACCOUNTS if acc["email"] not in env_emails]
        if not editable:
            edit_message(chat_id, msg_id, "Aucun compte administrateur modifiable (les comptes d'environnement sont protégés).")
            return
        keyboard = {"inline_keyboard": [[{"text": acc["email"], "callback_data": f"del_{acc['email']}"}] for acc in editable]}
        edit_message(chat_id, msg_id, "Choisir le compte à supprimer:", reply_markup=keyboard)
    elif data.startswith("del_"):
        email = data[4:]
        remove_smtp_account(chat_id, email)
        edit_message(chat_id, msg_id, f"✅ Supprimé: {email}")
    elif data == "admin_list_smtp":
        list_smtp_accounts(chat_id)
    elif data == "admin_add_recipient":
        user_sessions[user_id] = {"step": "admin_add_recipient", "data": {}, "timestamp": time.time()}
        edit_message(chat_id, msg_id, "📧 Envoyez l'email destinataire:")
    elif data == "admin_del_recipient":
        if not WHATSAPP_RECIPIENTS:
            edit_message(chat_id, msg_id, "Aucun destinataire.")
            return
        keyboard = {"inline_keyboard": [[{"text": r, "callback_data": f"delrec_{r}"}] for r in WHATSAPP_RECIPIENTS]}
        edit_message(chat_id, msg_id, "Choisir le destinataire à supprimer:", reply_markup=keyboard)
    elif data.startswith("delrec_"):
        email = data[7:]
        remove_recipient(chat_id, email)
        edit_message(chat_id, msg_id, f"✅ Supprimé: {email}")
    elif data == "admin_list_recipients":
        list_recipients(chat_id)
    elif data == "admin_stats":
        admin_stats(chat_id)

# ================= SERVEUR HTTP =================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is running")
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        pass

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"✅ Serveur HTTP démarré sur le port {PORT}")
    server.serve_forever()

# ================= MAIN =================
def main():
    def periodic_clean():
        while True:
            time.sleep(60)
            clean_sessions()
            if int(time.time()) % 600 < 60:
                invalid_smtp.clear()

    threading.Thread(target=periodic_clean, daemon=True).start()
    threading.Thread(target=run_http_server, daemon=True).start()

    print("🤖 WhatsApp Reporter Bot (Gmail API)")
    print(f"   Canal: {CHANNEL_USERNAME}")
    print(f"   Admin: {ADMIN_ID}")
    print(f"   Comptes Gmail: {len(SMTP_ACCOUNTS)}")
    print(f"   Destinataires: {len(WHATSAPP_RECIPIENTS)}")
    print(f"   Plage auto: {MIN_REPORTS}-{MAX_REPORTS}, délai: {EMAIL_DELAY}s, limite/heure: {MAX_REPORTS_PER_HOUR}")

    test_smtp_connection()

    last_id = 0
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"timeout": 30, "offset": last_id + 1},
                timeout=35,
            ).json()
            if resp.get("ok"):
                for upd in resp["result"]:
                    last_id = upd["update_id"]
                    if "callback_query" in upd:
                        handle_callback(upd["callback_query"])
                    elif "message" in upd:
                        msg = upd["message"]
                        text = msg.get("text", "")
                        if text.startswith("/"):
                            handle_command(msg["chat"]["id"], msg["from"]["id"], text.split()[0].lower())
                        else:
                            handle_text(msg["chat"]["id"], msg["from"]["id"], text)
        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            print(f"Erreur polling: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
