# Synthèse LCR → Excel

Micro-service ZoomAli.io / MultiBrasServices : extrait les opérations d'un ou
plusieurs relevés LCR PDF (banque Chabrières), permet de pointer les opérations
déjà saisies, affiche une synthèse + un graphique interactif, et exporte le tout
en Excel (avec histogramme empilé par date et par tireur).

Remplace l'ancienne app Streamlit. Architecture identique à `rm-expert-journal-ventes` :
**FastAPI sert à la fois l'API et un front HTML/JS vanilla** — un seul conteneur.

## Architecture

```
app/
├── main.py       FastAPI : GET / · /login.html · /config.js · POST /parse · /export
├── parser.py     Extraction déterministe des relevés LCR (pdfplumber)
├── exporter.py   Génération du classeur Excel (pandas + XlsxWriter)
└── static/
    ├── index.html  SPA vanilla (Supabase JS + Chart.js via CDN)
    ├── login.html  Page de login locale brandée (filigrane logo)
    └── images/     logo
```

| Méthode | Route         | Auth            | Rôle                                            |
|---------|---------------|-----------------|-------------------------------------------------|
| GET     | `/`           | non             | Application (HTML)                              |
| GET     | `/login.html` | non             | Page de login locale brandée                    |
| GET     | `/config.js`  | non             | Injecte la config runtime (`window.LCR_CONFIG`) |
| POST    | `/parse`      | **JWT + accès** | PDF(s) → JSON des opérations extraites          |
| POST    | `/export`     | **JWT + accès** | JSON (lignes éditées) → fichier `.xlsx`         |

## Contrôle d'accès (deux niveaux)

- **Front (UX)** : cookie SSO `.zoomali.io`, redirection vers `LOGIN_URL` (page de
  login locale brandée) si pas de session, overlay « accès non autorisé » si pas
  de ligne `user_services`. La page `/login.html` redirige seule vers l'app si une
  session SSO existe déjà (connexion sur un autre service de l'écosystème).
- **Back (barrière réelle)** : `_require_auth` valide le JWT via
  `{SUPABASE_URL}/auth/v1/user`, puis exige une ligne
  `user_services(user_id, SERVICE_ID)` → `401` / `403` sinon.

Toutes les données sont traitées **en mémoire** (aucune table métier, donc pas de
RLS à poser) : le verrou `user_services` côté backend est la barrière.

## Développement local

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env        # puis renseigner SUPABASE_URL / SUPABASE_ANON_KEY
uvicorn app.main:app --reload --port 8000
# http://localhost:8000  (le SSO cookie ne s'applique qu'en .zoomali.io,
#  en local le storage retombe sur localStorage)
```

## Déploiement Coolify (VPS OVH)

Build via le `Dockerfile` (Python 3.12 slim, single-stage, port `8000`).
Domaine : **lcr.zoomali.io**.

Variables d'environnement à configurer dans Coolify :

| Variable            | Portée            | Exemple                              |
|---------------------|-------------------|--------------------------------------|
| `SUPABASE_URL`      | partagée (équipe) | `https://…`                          |
| `SUPABASE_ANON_KEY` | partagée (équipe) | `eyJ…`                               |
| `SERVICE_ID`        | locale            | `18`                                 |
| `LOGIN_URL`         | locale            | `https://lcr.zoomali.io/login.html`  |
| `PORTAL_URL`        | locale            | `https://saaas.zoomali.io`           |

## Format source

Relevés LCR PDF de la banque Chabrières (tableau vectoriel). Extraction par
position de colonnes : tireur, date d'échéance (`JJ/MM/AA`), n° opération,
montant. Les lignes à date illisible sont écartées.
