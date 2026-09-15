# lcr — règles pour l'agent qui reprend ce dépôt

Service `lcr.zoomali.io` (n° 18 au portail) : relevés LCR/BOR Banque Chabrières (PDF) →
écriture JoGADM 11 colonnes, contrôle anti-doublon contre le FEC. Python/FastAPI, déployé
par Coolify OVH sur `main` (uuid `bahhlyso06vgow0y5tnvmjv1`). Les clients : l'écran, et
`erb.zoomali.io` qui l'appelle par le bras `ged-erb` pour tous les relevés d'un dossier.

## Avant de coder

1. Lire `journal.md` (ce qui a été fait, daté) et `README.md` (routes, règles métier).
2. Les tests : `python3 -m pytest -q tests` dans un venv (**pandas** et **pytest** dedans),
   jamais en global. Huit tests au 12/09/2026 ; on n'en retire aucun.
3. La version : `~/.agents/scripts/version-zoomali.sh 18 <jj.mm.aa-n> /atelier/projets/lcr`
   — il lit `APP_VERSION` dans `app/main.py` et pose la vignette du portail. Une version par
   commit qui change le comportement.
4. Pousser = déployer. Après le push, lire la version en ligne :
   `curl -s https://lcr.zoomali.io/openapi.json | python3 -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"`.

## Les règles métier qui ne bougent pas (le Chef)

- **1 relevé = 1 écriture** : les 401 des tireurs, puis la 512 du total.
- **1 écriture = 1 date** (12/09/2026). La GADM refuse un bloc à dates mélangées. Un PDF
  Chabrières peut contenir **plusieurs relevés** (une « Date de règlement » par page impaire,
  pages paires = mentions légales) : le regroupement se fait sur (`releve`, `echeance`) et
  `controler_dates` refuse tout bloc mélangé. Ne jamais revenir au regroupement par fichier.
- `date_piece`, si fourni, date **toutes** les lignes du bloc ; `Echeance` garde l'échéance.
- Déterministe : aucun compte deviné ; un tireur inconnu est signalé (`EcritureIncomplete`).
- Le FEC exporté par la GADM a pour séparateur `|` (lu depuis 12.09.26-2), à côté de `\t` et `;`.

## Pièges payés

- `.volets/` et `BRIEF.md` sont le poste de travail d'un bras : ignorés par git, pas livrés.
- Un bras lancé sur ce dépôt a exécuté des consignes qui n'étaient pas pour lui (12/09) :
  voir la compétence `planificateur-executant`, § « Le volet reçoit aussi… ».

## Règle écosystème (15/09/2026) — la nature devant le libellé

Le FEC n'a pas de colonne nature : `Libéllé1` commence par elle. Ici c'est déjà fait
(`LCR mm.aa` sur toutes les lignes) — **ne pas l'enlever**. Le reste de la règle (VI, PR, CQ,
EP, CB EX / SC / CK) vit dans `erb/src/engine/nature.ts` et la skill `gadm-ecriture-format`.
