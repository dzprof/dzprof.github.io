# -*- coding: utf-8 -*-
"""
Générateur de journaux_index.json

Utilisation : placer ce fichier dans le même dossier que index.html et le dossier JOURNAUX,
puis lancer : python generer_index.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from datetime import datetime

try:
    import fitz  # PyMuPDF
except Exception:
    print("ERREUR : PyMuPDF n'est pas installé.")
    print("Installez-le avec : python -m pip install PyMuPDF")
    raise

ROOT = Path(__file__).resolve().parent
JOURNAUX_DIR = ROOT / "JOURNAUX"
OUT = ROOT / "journaux_index.json"
SPLIT_DIR = ROOT / "journaux_index"
YEARS = [str(y) for y in range(2016, 2029)]

ISSN_RE = re.compile(r"(?<!\d)(\d{4})\s*[-–— ]?\s*(\d{3}[0-9Xx])(?!\d)")
ROW_NUM_RE = re.compile(r"^\d{1,6}$")
BAD_WORDS = re.compile(
    r"^(\s*|no\.?|n°|nº|issn|e-issn|eissn|journal title|title|publisher|publisher name|editeur|éditeur|"
    r"country|language|subject|category|source|rank|page|sjr|snip|citescore|print|online)$",
    re.I,
)
BAD_HEADERS = re.compile(r"^(n°|no|nº|journal title|title|issn|e-issn|eissn|publisher name|publisher|editeur|éditeur)\b", re.I)
PUBLISHER_LINE = re.compile(
    r"^(ELSEVIER|SPRINGER|WILEY|TAYLOR\s*&?\s*FRANCIS|SAGE|IEEE|ACM|"
    r"OXFORD\s+UNIV|CAMBRIDGE\s+UNIV|NATURE\s+PUBLISHING|MDPI|HINDAWI|"
    r"DE\s+GRUYTER|ASME|IOP|BRILL|EMERALD|FRONTIERS|PLOS|BIOMED|"
    r"LIPPINCOTT|WALTER|TECHNO-PRESS|KEAI|OPTICA|SCIENCE\s+PRESS|"
    r"AMERICAN\s+CHEMICAL\s+SOCIETY|ROYAL\s+SOCIETY\s+OF\s+CHEMISTRY|"
    r"BMJ\s+PUBLISHING|MARY\s+ANN\s+LIEBERT|WORLD\s+SCIENTIFIC|"
    r"KLUWER|BLACKWELL|IOS\s+PRESS|JOHN\s+WILEY|AIP\b).*$",
    re.I,
)
PUBLISHER_TAIL = re.compile(
    r"\b(ELSEVIER(?:\s+SCIENCE)?(?:\s+(?:BV|B V|INC|LTD))?|SPRINGER(?:\s+(?:NATURE|VERLAG))?|"
    r"WILEY(?:\s+BLACKWELL)?|TAYLOR\s*&?\s*FRANCIS|SAGE(?:\s+PUBLICATIONS)?|IEEE|ACM|"
    r"OXFORD\s+UNIV(?:ERSITY)?\s+PRESS|CAMBRIDGE\s+UNIV(?:ERSITY)?\s+PRESS|NATURE\s+PUBLISHING\s+GROUP|"
    r"MDPI|HINDAWI|DE\s+GRUYTER|ASME|IOP\s+PUBLISHING|BRILL|EMERALD|FRONTIERS|PLOS|BIOMED\s+CENTRAL)\b.*$",
    re.I,
)


def norm_path(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def clean(s: str) -> str:
    s = str(s or "")
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip(" -–—:;,.\t\r\n")
    return s.strip()


def normalize_issn(s: str) -> str:
    raw = re.sub(r"[^0-9Xx]", "", str(s or "")).upper()
    if len(raw) != 8:
        return ""
    return raw[:4] + "-" + raw[4:]


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def category_from_path(path: Path) -> str:
    p = path.as_posix().lower()
    parts = [x.lower() for x in path.parts]
    if "predat" in p or "prédat" in p or "predateur" in p or "prédateur" in p or "predatrice" in p or "prédatrice" in p:
        return "PRED"
    if any(x in ("a+", "a plus", "aplus") for x in parts):
        return "AP"
    if any(x == "a" for x in parts):
        return "A"
    if any(x == "b" for x in parts):
        return "B"
    return "OTHER"


def year_from_path(path: Path) -> str:
    for part in path.parts:
        if re.fullmatch(r"20\d{2}", part):
            return part
    return ""


def source_name(path: Path) -> str:
    return clean(path.stem.replace("_", " ").replace("-", " "))


def likely_title(s: str) -> bool:
    s = clean(s)
    if len(s) < 4 or len(s) > 250:
        return False
    if ISSN_RE.search(s):
        return False
    if BAD_WORDS.match(s) or BAD_HEADERS.match(s):
        return False
    if PUBLISHER_LINE.match(s):
        return False
    if re.fullmatch(r"[\d\W_]+", s):
        return False
    if not re.search(r"[A-Za-zÀ-ÿ]", s):
        return False
    letters = len(re.findall(r"[A-Za-zÀ-ÿ]", s))
    digits = len(re.findall(r"\d", s))
    if digits > letters and letters < 12:
        return False
    return True


def title_before_issn(line: str, issn: str) -> str:
    line = clean(line)
    pos = line.upper().find(issn.upper())
    before = line[:pos] if pos >= 0 else line
    before = ISSN_RE.sub(" ", before)
    before = re.sub(r"\b(N°|NO|Nº|JOURNAL TITLE|TITLE|TITRE DE LA REVUE|PUBLISHER|ISSN|E-ISSN|EISSN)\b", " ", before, flags=re.I)
    matches = list(re.finditer(r"(?:^|\s)(\d{1,6})\s+", before))
    if matches:
        before = before[matches[-1].end():]
    before = PUBLISHER_TAIL.sub("", before)
    before = clean(before)
    if likely_title(before):
        return before
    return ""


def find_nearby_title(lines: list[str], idx: int, line: str, issn: str) -> str:
    t = title_before_issn(line, issn)
    if t:
        return t

    # Recherche par bloc : remonter jusqu'au numéro d'ordre (ex: "349") ou début de bloc
    start_k = -1
    for k in range(idx - 1, max(-1, idx - 15), -1):
        cand = clean(lines[k])
        if ROW_NUM_RE.match(cand):
            start_k = k
            break
        if ISSN_RE.search(cand) and k < idx - 2:
            start_k = k
            break

    if start_k >= 0:
        candidate_lines = []
        for k in range(start_k + 1, idx):
            l = clean(lines[k])
            if ISSN_RE.search(l):
                continue
            if BAD_WORDS.match(l) or BAD_HEADERS.match(l):
                continue
            if PUBLISHER_LINE.match(l):
                continue
            candidate_lines.append(l)
        if candidate_lines:
            joined = clean(" ".join(candidate_lines))
            if likely_title(joined):
                return joined

    # Secours : chercher une ligne isolée au-dessus puis au-dessous
    for d in range(1, 7):
        j = idx - d
        if 0 <= j < len(lines):
            cand = clean(lines[j])
            cand = re.sub(r"^\d+\s+", "", cand)
            cand = PUBLISHER_TAIL.sub("", cand)
            cand = clean(cand)
            if likely_title(cand):
                return cand
    for d in range(1, 4):
        j = idx + d
        if 0 <= j < len(lines):
            cand = clean(lines[j])
            cand = re.sub(r"^\d+\s+", "", cand)
            cand = PUBLISHER_TAIL.sub("", cand)
            cand = clean(cand)
            if likely_title(cand):
                return cand
    return ""


def extract_lines_from_pdf(pdf_path: Path) -> list[tuple[int, list[str]]]:
    pages = []
    doc = fitz.open(pdf_path)
    try:
        for page_number, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            lines = [clean(x) for x in text.splitlines()]
            lines = [x for x in lines if x]
            pages.append((page_number, lines))
    finally:
        doc.close()
    return pages


def add_record(records: list[dict], seen: set[tuple], *, year: str, cat: str, title: str, issn: str, src: str, path: str, page: int, text: str = ""):
    title = clean(title)
    issn = normalize_issn(issn)
    text = clean(text or title)
    key = (year, cat, normalize_text(title), issn, src, page)
    if key in seen:
        return
    if not title and not issn and not text:
        return
    seen.add(key)
    records.append({
        "annee": year,
        "categorie": "A+" if cat == "AP" else cat,
        "titre": title,
        "issn": issn,
        "source": src,
        "path": path,
        "page": page,
        "texte": text,
    })


def generate() -> list[dict]:
    if not JOURNAUX_DIR.exists():
        raise SystemExit(f"Dossier introuvable : {JOURNAUX_DIR}")

    pdfs = sorted(JOURNAUX_DIR.rglob("*.pdf"))
    if not pdfs:
        raise SystemExit("Aucun PDF trouvé dans le dossier JOURNAUX.")

    records: list[dict] = []
    seen: set[tuple] = set()

    print(f"PDF trouvés : {len(pdfs)}")
    for pdf in pdfs:
        year = year_from_path(pdf)
        cat = category_from_path(pdf)
        if year not in YEARS or cat not in {"AP", "A", "B", "PRED"}:
            continue
        src = source_name(pdf)
        path = norm_path(pdf)
        print(f"Lecture : {path} [{year} / {cat}]")
        try:
            pages = extract_lines_from_pdf(pdf)
        except Exception as e:
            print(f"  ERREUR lecture PDF : {e}")
            continue

        for page_no, lines in pages:
            page_text = " ".join(lines)
            # Entrées avec ISSN.
            for i, line in enumerate(lines):
                for m in ISSN_RE.finditer(line):
                    issn = f"{m.group(1)}-{m.group(2).upper()}"
                    title = find_nearby_title(lines, i, line, issn)
                    if not title:
                        title = clean(line.replace(issn, ""))
                    add_record(records, seen, year=year, cat=cat, title=title, issn=issn, src=src, path=path, page=page_no, text=line)

            # Pour les listes prédatrices sans ISSN : enregistrer des lignes de titre/éditeur.
            if cat == "PRED":
                for line in lines:
                    candidate = clean(re.sub(r"^\d+[.)-]?\s+", "", line))
                    if likely_title(candidate):
                        add_record(records, seen, year=year, cat=cat, title=candidate, issn="", src=src, path=path, page=page_no, text=page_text[:1200])

    return records


def main() -> int:
    print("Génération des index de journaux")
    print(f"Racine : {ROOT}")
    records = generate()
    records.sort(key=lambda r: (r["annee"], r["categorie"], r["titre"], r["issn"], r["source"]))
    now_iso = datetime.now().isoformat(timespec="seconds")
    data = {
        "generated_at": now_iso,
        "count": len(records),
        "records": records,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK : {OUT.name} créé avec {len(records)} entrées.")

    SPLIT_DIR.mkdir(exist_ok=True)
    by_year: dict[str, list[dict]] = {}
    predatory_records: list[dict] = []
    seen_pred: set[tuple] = set()

    for r in records:
        y = r["annee"]
        by_year.setdefault(y, []).append(r)
        if r.get("categorie") in ("PRED", "PREDATRICE"):
            key = (r.get("annee", ""), r.get("issn", "").upper(), r.get("titre", "").strip().lower(), r.get("source", ""))
            if key not in seen_pred:
                seen_pred.add(key)
                predatory_records.append(r)

    # Compléter les années futures manquantes (ex: 2027, 2028) avec la dernière année disponible
    available_years = sorted([y for y in by_year.keys() if by_year[y]])
    if available_years:
        latest_y = available_years[-1]
        for y in YEARS:
            if y not in by_year or not by_year[y]:
                cloned = []
                for r in by_year[latest_y]:
                    r_copy = dict(r)
                    r_copy["annee"] = y
                    cloned.append(r_copy)
                by_year[y] = cloned

    # 1) Fichiers annuels découpés
    for y, y_recs in sorted(by_year.items()):
        y_path = SPLIT_DIR / f"{y}.json"
        y_data = {
            "generated_at": now_iso,
            "year": y,
            "count": len(y_recs),
            "records": y_recs,
        }
        y_path.write_text(json.dumps(y_data, ensure_ascii=False), encoding="utf-8")

    # 2) Fichier dédié prédateurs (2016-2028)
    pred_path = SPLIT_DIR / "predatrices.json"
    pred_data = {
        "generated_at": now_iso,
        "count": len(predatory_records),
        "records": predatory_records,
    }
    pred_path.write_text(json.dumps(pred_data, ensure_ascii=False), encoding="utf-8")

    # 3) Manifeste JSON
    manifest_path = SPLIT_DIR / "manifest.json"
    manifest_data = {
        "generated_at": now_iso,
        "years": sorted(by_year.keys()),
        "total_count": len(records),
        "by_year": {y: len(recs) for y, recs in sorted(by_year.items())},
        "predatory_count": len(predatory_records),
        "format": "one_json_file_per_year_v53_details",
    }
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK : dossier {SPLIT_DIR.name}/ mis à jour avec {len(by_year)} années, {len(predatory_records)} entrées prédatrices, et manifest.json.")
    print("Entrées par année :")
    for y in sorted(by_year):
        print(f"  {y} : {len(by_year[y])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
