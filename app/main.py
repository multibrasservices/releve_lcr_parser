import os
import urllib.parse
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.ecriture import EcritureIncomplete, construire_ecriture, tsv_jogadm
from app.exporter import build_xlsx, build_xlsx_gadm
from app.parser import parse_lcr

APP_VERSION = "2026.06.18-1"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
# service_id de cet outil dans la table `services` (verrou d'accès user_services).
SERVICE_ID = int(os.environ.get("SERVICE_ID", "18"))
# Portail de l'écosystème (« Retour aux outils ») — URL stable, pas un paramètre
# d'environnement. La page de login est servie localement (/login.html, relatif).
PORTAL_URL = "https://saaas.zoomali.io"

app = FastAPI(title="Synthèse LCR → Excel", version=APP_VERSION, docs_url=None, redoc_url=None)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/login.html", response_class=HTMLResponse)
async def login():
    """Page de login locale brandée (règle 18.1 : chaque sous-domaine a SA page /login)."""
    return (STATIC_DIR / "login.html").read_text(encoding="utf-8")


@app.get("/config.js")
async def config_js():
    """Config runtime injectée depuis les vars d'env Coolify."""
    content = (
        f"window.LCR_CONFIG = {{"
        f' SUPABASE_URL: "{SUPABASE_URL}",'
        f' SUPABASE_ANON_KEY: "{SUPABASE_ANON_KEY}",'
        f" SERVICE_ID: {SERVICE_ID},"
        f' PORTAL_URL: "{PORTAL_URL}",'
        f' VERSION: "{APP_VERSION}"'
        f" }};"
    )
    return Response(content=content, media_type="application/javascript")


async def _require_auth(authorization: str = Header(default="")) -> str:
    """Valide le JWT Supabase ET l'accès à cet outil (user_services).

    Barrière réelle côté serveur : le cookie SSO `.zoomali.io` est cross-domain,
    donc un JWT valide ne suffit pas — il faut une ligne `user_services` pour ce
    `SERVICE_ID`. Lève 401 (non authentifié) ou 403 (authentifié mais non autorisé).
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Non authentifié.")
    token = authorization[len("Bearer "):]
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail="Configuration Supabase manquante.")

    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Session expirée ou invalide.")
        user_id = resp.json().get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Session invalide.")

        # Verrou d'accès : une ligne user_services (user_id, service_id) doit exister.
        try:
            access = await client.get(
                f"{SUPABASE_URL}/rest/v1/user_services",
                params={
                    "user_id": f"eq.{user_id}",
                    "service_id": f"eq.{SERVICE_ID}",
                    "select": "user_id",
                },
                headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
            )
        except Exception as e:
            # Ne jamais avaler silencieusement : un échec réseau ne doit pas ouvrir l'accès.
            print(f"[ERR _require_auth user_services] {e}")
            raise HTTPException(status_code=503, detail="Vérification d'accès indisponible.")

    if access.status_code != 200 or not access.json():
        raise HTTPException(status_code=403, detail="Accès non autorisé à cet outil.")
    return token


@app.post("/parse")
async def parse(
    files: list[UploadFile] = File(...),
    authorization: str = Header(default=""),
):
    """Extrait les opérations d'un ou plusieurs relevés LCR PDF."""
    await _require_auth(authorization)

    all_rows: list[dict] = []
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"« {file.filename} » n'est pas un PDF.")
        pdf_bytes = await file.read()
        if len(pdf_bytes) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"« {file.filename} » dépasse 20 Mo.")
        try:
            all_rows.extend(parse_lcr(pdf_bytes))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur de lecture de « {file.filename} » : {e}")

    if not all_rows:
        raise HTTPException(
            status_code=400,
            detail="Aucune opération extraite. Vérifiez que les PDF sont bien des relevés LCR.",
        )

    all_rows.sort(key=lambda r: r["echeance"])
    return {"rows": all_rows, "count": len(all_rows)}


@app.post("/gadm")
async def gadm(
    payload: dict = Body(...),
    authorization: str = Header(default=""),
):
    """
    Opérations + société + comptes des tireurs → écriture JoGADM (1 PDF = 1 écriture).
    Renvoie 400 avec la liste des tireurs à paramétrer si le mapping est incomplet.
    """
    await _require_auth(authorization)
    try:
        lignes = construire_ecriture(
            payload.get("rows") or [],
            payload.get("societe") or {},
            payload.get("comptes") or {},
            payload.get("date_piece"),
        )
    except EcritureIncomplete as e:
        raise HTTPException(status_code=400, detail={"tireurs_manquants": e.tireurs})
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"lignes": lignes, "tsv": tsv_jogadm(lignes)}


@app.post("/gadm/xlsx")
async def gadm_xlsx(
    payload: dict = Body(...),
    authorization: str = Header(default=""),
):
    """Même écriture, livrée en classeur Excel 11 colonnes (collable dans la GADM)."""
    await _require_auth(authorization)
    try:
        lignes = construire_ecriture(
            payload.get("rows") or [],
            payload.get("societe") or {},
            payload.get("comptes") or {},
            payload.get("date_piece"),
        )
    except EcritureIncomplete as e:
        raise HTTPException(status_code=400, detail={"tireurs_manquants": e.tireurs})
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    nom = urllib.parse.quote(f"{payload.get('filename') or 'GADM_LCR'}.xlsx")
    return Response(
        content=build_xlsx_gadm(lignes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{nom}"},
    )


@app.post("/export")
async def export(
    payload: dict = Body(...),
    authorization: str = Header(default=""),
):
    """Génère le fichier Excel de synthèse à partir des lignes (éventuellement éditées)."""
    await _require_auth(authorization)

    rows = payload.get("rows") or []
    if not rows:
        raise HTTPException(status_code=400, detail="Aucune donnée à exporter.")

    filename = payload.get("filename") or "synthese_lcr"
    try:
        xlsx_bytes = build_xlsx(rows)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de génération du fichier : {e}")

    xlsx_name = urllib.parse.quote(f"{filename}.xlsx")
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{xlsx_name}"},
    )
