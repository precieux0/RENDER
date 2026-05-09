#!/usr/bin/env python3
"""
get_refresh_tokens.py - Obtient un refresh_token Gmail pour plusieurs comptes.
Corrigé : utilise un port aléatoire et ferme correctement le serveur après chaque code.
"""

import json
import urllib.parse
import webbrowser
import http.server
import socketserver
import threading
import requests

SCOPE = "https://www.googleapis.com/auth/gmail.send"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

def grab_code(port):
    """Démarre un serveur local sur le port donné pour capter le code redirigé par Google."""
    code_holder = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            if "code" in params:
                code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK, vous pouvez fermer cet onglet.")
            else:
                self.send_response(400)
                self.end_headers()
        def log_message(self, *a, **k):
            pass

    server = socketserver.TCPServer(("localhost", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    while "code" not in code_holder:
        pass
    server.shutdown()
    server.server_close()  # libère explicitement le port
    return code_holder["code"]

def get_refresh_token(client_id, client_secret, port):
    params = {
        "client_id": client_id,
        "redirect_uri": f"http://localhost:{port}",
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    print("\n👉 Ouvre l'URL et connecte-toi AVEC LE GMAIL VOULU :")
    print(url)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    code = grab_code(port)
    r = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": f"http://localhost:{port}",
        "grant_type": "authorization_code",
    }, timeout=20)
    r.raise_for_status()
    return r.json()["refresh_token"]

def main():
    client_id = input("client_id Google : ").strip()
    client_secret = input("client_secret Google : ").strip()
    accounts = []
    # choisis un port de base aléatoire pour éviter les conflits
    import random
    base_port = random.randint(8000, 9000)

    compteur = 0
    while True:
        email = input("\nAdresse Gmail (vide pour terminer) : ").strip()
        if not email:
            break
        print(f"-> Authentifie-toi avec {email}")
        port = base_port + compteur  # change de port à chaque compte
        rt = get_refresh_token(client_id, client_secret, port)
        accounts.append({
            "email": email,
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": rt,
        })
        print(f"✅ refresh_token obtenu pour {email}")
        compteur += 1

    print("\n=== Copie ceci dans la variable d'environnement SMTP_ACCOUNTS ===\n")
    print(json.dumps(accounts, indent=2))

if __name__ == "__main__":
    main()