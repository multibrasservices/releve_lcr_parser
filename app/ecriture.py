"""Relevé LCR → écriture comptable au format JoGADM (11 colonnes).

Règle métier (Chef, 27/07/2026) : **1 PDF = 1 écriture**
  - N lignes 401 au DÉBIT : une par opération du relevé, sur le compte du tireur
  - 1 ligne 512 au CRÉDIT : le total prélevé par la banque

Et **une écriture n'a qu'une date** (Chef, 12/09/2026) : la GADM refuse un bloc dont
les lignes portent des dates différentes. Un PDF qui contient plusieurs relevés à des
échéances différentes donne donc plusieurs écritures, une par échéance.

100 % déterministe (règle 10) : aucune IA, aucun compte deviné. Un tireur absent du
paramétrage est signalé, jamais imputé au hasard.

Les montants sont manipulés en CENTIMES (entiers) : l'équilibre ΣD = ΣC se contrôle
exactement, sans flottant qui dérive.
"""
from datetime import datetime

COLONNES_JOGADM = [
    "Date", "Jo", "Nature", "Pcg", "Pièce", "Libéllé1", "Libéllé2",
    "D", "C", "Règlement", "Echeance",
]

LIB_MAX = 20  # la GADM tronque au-delà


class EcritureIncomplete(Exception):
    """Tireurs sans compte 401 paramétré : on refuse de produire l'écriture."""

    def __init__(self, tireurs):
        self.tireurs = sorted(tireurs)
        super().__init__(
            "Tireur(s) sans compte 401 : " + ", ".join(self.tireurs)
        )


def normaliser_tireur(nom):
    """Clé de rapprochement : majuscules, espaces compactés (le PDF est irrégulier)."""
    return " ".join(str(nom or "").split()).upper()


def pcg8(compte):
    """
    Compte général sur 8 caractères, complété par des zéros à droite (`6156` → `61560000`).
    Indispensable : une longueur ≠ 8 fait basculer la ligne en analytique côté GADM, et
    la colonne char(8) de Postgres complète avec des ESPACES — jamais un compte valide.
    """
    chiffres = "".join(c for c in str(compte or "") if c.isdigit())
    if not chiffres:
        raise ValueError(f"Compte invalide : « {compte} »")
    return (chiffres + "00000000")[:8]


def _centimes(montant):
    return int(round(float(montant) * 100))


def _jj_mm_aaaa(iso):
    """'2026-07-24' → '24/07/2026' (format attendu par la GADM)."""
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def _montant(cents):
    return f"{cents / 100:.2f}" if cents else ""


def date_ecriture(lignes):
    """Date du relevé = échéance la plus tardive (sert à la ligne 512 et au libellé)."""
    return max(l["echeance"] for l in lignes)


def construire_ecriture(lignes, societe, comptes_tireurs, date_piece=None, piece=""):
    """
    lignes           : sortie de parse_lcr (echeance, tireur, operation, montant, releve)
    societe          : {nom, pcg_512, code_journal, nature, reglement}
    comptes_tireurs  : {tireur normalisé: compte 401}
    date_piece       : force la colonne Date de TOUTES les lignes (401 et 512) ;
                       la colonne Echeance garde l'échéance réelle de chaque effet

    **1 relevé = 1 écriture** : chaque relevé chargé produit ses lignes 401 SUIVIES
    de SA ligne 512. Charger 3 relevés donne donc 3 lignes 512, pas une seule —
    sinon les trois prélèvements bancaires seraient soldés par un seul mouvement.

    **1 écriture = 1 date** : le regroupement se fait sur (`releve`, `echeance`).
    Un PDF à deux dates de règlement (cas BAKITO 12/09/2026) donne deux écritures,
    chacune datée de son échéance ; un PDF à une seule échéance, une seule — comme avant.

    Retourne la liste des lignes JoGADM (dicts, 11 colonnes).
    Lève EcritureIncomplete si un tireur n'a pas de compte.
    """
    if not lignes:
        raise ValueError("Aucune opération à comptabiliser.")

    manquants = {normaliser_tireur(l["tireur"]) for l in lignes
                 if normaliser_tireur(l["tireur"]) not in comptes_tireurs}
    if manquants:
        raise EcritureIncomplete(manquants)

    jo = str(societe.get("code_journal") or "").strip()
    nature = (societe.get("nature") or "DI").strip()
    reglement = (societe.get("reglement") or "CA").strip()

    # un groupe = un relevé ET une échéance : toutes ses lignes portent la même date
    groupes = {}
    for ligne in lignes:
        groupes.setdefault((ligne.get("releve") or "", ligne["echeance"]), []).append(ligne)

    ecriture = []
    for cle in sorted(groupes, key=lambda k: (date_ecriture(groupes[k]), k[0])):
        du_releve = groupes[cle]
        date_releve = _jj_mm_aaaa(date_piece or date_ecriture(du_releve))
        total = 0
        for ligne in du_releve:
            cents = _centimes(ligne["montant"])
            total += cents
            echeance = _jj_mm_aaaa(ligne["echeance"])
            ecriture.append({
                # date d'écriture = échéance de l'effet (règle Chef : les deux dates
                # sont celles du relevé, jamais une date de traitement) — ou la
                # date_piece imposée, la même pour tout le bloc
                "Date": date_releve,
                "Jo": jo,
                "Nature": nature,
                "Pcg": pcg8(comptes_tireurs[normaliser_tireur(ligne["tireur"])]),
                "Pièce": piece,
                # Lib1 : « LCR mm.aa » sur TOUTES les lignes ; Lib2 : le fournisseur
                "Libéllé1": f"LCR {echeance[3:5]}.{echeance[8:]}"[:LIB_MAX],
                "Libéllé2": str(ligne["tireur"]).strip()[:LIB_MAX],
                "D": _montant(cents),
                "C": "",
                "Règlement": reglement,
                "Echeance": echeance,
            })

        ecriture.append({
            "Date": date_releve,
            "Jo": jo,
            "Nature": nature,
            "Pcg": pcg8(societe["pcg_512"]),
            "Pièce": piece,
            "Libéllé1": f"LCR {date_releve[3:5]}.{date_releve[8:]}"[:LIB_MAX],
            "Libéllé2": str(societe.get("nom") or "")[:LIB_MAX],
            "D": "",
            "C": _montant(total),
            "Règlement": reglement,
            "Echeance": _jj_mm_aaaa(date_ecriture(du_releve)),
        })

    controler_equilibre(ecriture)
    controler_dates(ecriture)
    return ecriture


def controler_equilibre(ecriture):
    """ΣD = ΣC au centime, sinon on refuse de livrer (règle 11 : jamais en silence)."""
    somme = lambda col: sum(_centimes(l[col]) for l in ecriture if l[col])
    debit, credit = somme("D"), somme("C")
    if debit != credit:
        raise ValueError(
            f"Écriture déséquilibrée : débit {debit / 100:.2f} ≠ crédit {credit / 100:.2f}"
        )
    return debit


def controler_dates(ecriture):
    """
    Garde-fou : un bloc (les 401 jusqu'à leur 512) ne porte qu'une seule Date,
    sinon la GADM refuse l'import. Ne doit jamais se déclencher tant que le
    regroupement se fait par (releve, echeance) — il est là pour le jour où
    quelqu'un change ce regroupement.
    """
    bloc = []
    for ligne in ecriture:
        bloc.append(ligne["Date"])
        if ligne["C"]:  # la 512 clôt le bloc
            dates = sorted(set(bloc))
            if len(dates) > 1:
                raise ValueError(
                    f"Écriture du {ligne['Date']} : dates mélangées ({', '.join(dates)})"
                )
            bloc = []
    return True


def tsv_jogadm(ecriture):
    """Écriture → TSV 11 colonnes (contrat du pont vers gadm.zoomali.io)."""
    return "\n".join(
        "\t".join(str(ligne.get(col, "")) for col in COLONNES_JOGADM)
        for ligne in ecriture
    )
