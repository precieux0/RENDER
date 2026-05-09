# WA Reporter — migration SMTP → API Gmail (HTTPS)

Render bloque les ports SMTP 465/587. Le bot envoie désormais TOUS les emails
via l'**API Gmail** (HTTPS, port 443), avec OAuth2 et refresh tokens.
Aucune connexion SMTP n'est plus utilisée.

## Fichiers livrés

| Fichier | Rôle |
|---|---|
| `gmail_api.py` | Nouveau pool `GmailAPIPool` (remplace `smtp_pool.py`). API HTTPS uniquement. |
| `bot.py` | Patché : utilise `gmail_api`, ajoute `/test_smtp`, panneau admin adapté. |
| `config.py` | Inchangé fonctionnellement, on garde `SMTP_ACCOUNTS` (format différent). |
| `requirements.txt` | `requests`, `python-dotenv`. **Pas besoin de `google-api-python-client`** : on appelle l'API Gmail en REST. |
| `get_refresh_tokens.py` | Script local pour générer les `refresh_token` de chaque Gmail (à exécuter UNE FOIS sur ton PC). |

Tu peux supprimer `smtp_pool.py` du repo (plus utilisé).

## 1. Côté Google Cloud (une seule fois)

1. https://console.cloud.google.com → **Créer un projet** (n'importe quel nom).
2. **APIs & Services → Library** → activer **Gmail API**.
3. **APIs & Services → OAuth consent screen** :
   - Type : **External**, status **Testing** (suffisant).
   - Scope obligatoire : `https://www.googleapis.com/auth/gmail.send`.
   - **Test users** : ajoute CHAQUE adresse Gmail que tu vas utiliser
     (sinon l'autorisation sera refusée).
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Type : **Desktop app**.
   - Récupère `client_id` et `client_secret`.

> Tu peux réutiliser le même couple `client_id`/`client_secret` pour tous tes
> comptes Gmail. Seul le `refresh_token` est par compte.

## 2. Générer les refresh_token (en local)

```bash
pip install requests
python get_refresh_tokens.py
```

Le script :
1. te demande `client_id` et `client_secret` ;
2. pour chaque adresse Gmail, ouvre une URL d'autorisation ;
3. tu te connectes avec **le bon Gmail** et acceptes le scope `gmail.send` ;
4. à la fin, il imprime le JSON complet à coller dans la variable
   `SMTP_ACCOUNTS` sur Render.

## 3. Variables d'environnement Render

Le nom `SMTP_ACCOUNTS` est conservé pour ne rien casser, mais le **format
change** :

```env
TELEGRAM_TOKEN=123456:AA…
ADMIN_ID=7684684739

SMTP_ACCOUNTS=[{"email":"a@gmail.com","client_id":"xxx.apps.googleusercontent.com","client_secret":"GOCSPX-xxx","refresh_token":"1//0gxxx"},{"email":"b@gmail.com","client_id":"xxx.apps.googleusercontent.com","client_secret":"GOCSPX-xxx","refresh_token":"1//0gyyy"}]

WHATSAPP_RECIPIENTS=["support@support.whatsapp.com","abuse@whatsapp.com"]
MIN_REPORTS=10
MAX_REPORTS=50
EMAIL_DELAY=2.0
MAX_REPORTS_PER_HOUR=100
```

Tu peux **supprimer** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_SSL`, `SMTP_DEBUG` :
ils ne sont plus utilisés.

## 4. Comportement conservé

- Même rotation entre comptes (`random.choice` parmi les comptes valides).
- Même gestion des comptes en échec (`invalid_smtp` + `failures` interne).
- Mêmes délais entre envois (`EMAIL_DELAY`).
- Mêmes destinataires, mêmes templates (`generate_detailed_report`).
- Mêmes commandes Telegram (`/report`, `/autoreport`, `/stats`, `/admin`…).

## 5. Nouvelles commandes

- **`/test_smtp`** (admin uniquement) : teste chaque compte via l'API Gmail
  (refresh + appel `users.me/profile`). Renvoie la liste avec ✅ / ❌.
- Bouton **🧪 Test Gmail API** dans `/admin`.
- Bouton **➕ Ajouter Gmail (JSON)** : on colle directement un objet JSON
  `{"email":..., "client_id":..., "client_secret":..., "refresh_token":...}`.

## 6. Démarrage

Au boot, le bot exécute automatiquement `test_smtp_connection()` qui appelle
`gmail_pool.test_all()` — tu vois immédiatement dans les logs Render quels
comptes sont OK ou KO.

## 7. Capacité

Quota Gmail API par compte : ~250 quota units/seconde et 1 milliard/jour
(envoi = 100 units). En pratique tu peux envoyer ~500 emails/jour par compte
Gmail standard avant de risquer un blocage côté boîte. Avec N comptes, tu
multiplies d'autant. La rotation aléatoire répartit la charge.

## 8. Erreurs courantes

| Erreur | Cause | Fix |
|---|---|---|
| `400 invalid_grant` | `refresh_token` expiré ou compte non listé en Test users | Re-générer avec `get_refresh_tokens.py` et ajouter le compte en Test users |
| `403 Request had insufficient authentication scopes` | Mauvais scope OAuth | Vérifier `gmail.send` dans la consent screen |
| `403 access blocked` | Adresse pas dans Test users | Ajouter dans OAuth consent → Test users |
| `429` | Quota dépassé | Réduire la fréquence ou ajouter un compte |
