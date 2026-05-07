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
YEARS = [str(y) for y in range(2016, 2027)]

ISSN_RE = re.compile(r"(?<!\d)(\d{4})\s*[-–— ]?\s*(\d{3}[0-9Xx])(?!\d)")
BAD_WORDS = re.compile(
    r"^(\s*|no\.?|n°|nº|issn|e-issn|eissn|journal title|title|publisher|editeur|éditeur|"
    r"country|language|subject|category|source|rank|page|sjr|snip|citescore|print|online)$",
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
    if len(s) < 4 or len(s) > 180:
        return False
    if ISSN_RE.search(s):
        return False
    if BAD_WORDS.match(s):
        return False
    if re.fullmatch(r"[\d\W_]+", s):
        return False
    if not re.search(r"[A-Za-zÀ-ÿ]", s):
        return False
    # Évite les longues lignes de chiffres ou de numéros.
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
    # Si la ligne contient plusieurs entrées collées, prendre après le dernier numéro d'ordre.
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
    # Chercher juste au-dessus puis juste au-dessous.
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
    print("Génération de journaux_index.json")
    print(f"Racine : {ROOT}")
    records = generate()
    records.sort(key=lambda r: (r["annee"], r["categorie"], r["titre"], r["issn"], r["source"]))
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(records),
        "records": records,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    by_year: dict[str, int] = {}
    for r in records:
        by_year[r["annee"]] = by_year.get(r["annee"], 0) + 1
    print(f"OK : {OUT.name} créé avec {len(records)} entrées.")
    print("Entrées par année :")
    for y in sorted(by_year):
        print(f"  {y} : {by_year[y]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
