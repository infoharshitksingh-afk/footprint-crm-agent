"""
Step 1: read whatever the CRM exported and map it onto the canonical schema.

Input is a folder of CSV exports (one per object). The agent works out which
file is accounts / contacts / deals, matches headers by synonym, asks Claude
about anything it can't place, and saves the result to mapping.json so a human
can confirm or edit it once. After that the mapping is reused on every run.
"""
import csv
import json
from pathlib import Path

from .schema import FIELDS

OBJECT_HINTS = {
    "accounts": ["compan", "account", "organi", "org"],
    "contacts": ["contact", "people", "person", "lead"],
    "deals": ["deal", "opportunit", "pipeline"],
}


def _read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return reader.fieldnames or [], rows


def _guess_object(path, headers):
    stem = path.stem.lower()
    for obj, hints in OBJECT_HINTS.items():
        if any(h in stem for h in hints):
            return obj
    # fall back to header overlap
    lower = {h.strip().lower() for h in headers}
    scores = {obj: sum(1 for syns in f.values() if lower & set(syns)) for obj, f in FIELDS.items()}
    return max(scores, key=scores.get)


def _match_headers(obj, headers):
    """Synonym match. Returns (mapping canonical->header, unmapped headers)."""
    mapping, used = {}, set()
    lower = {h: h.strip().lower() for h in headers}
    for canon, syns in FIELDS[obj].items():
        for syn in syns:  # synonyms are ordered by preference
            hit = next((h for h, l in lower.items() if l == syn and h not in used), None)
            if hit:
                mapping[canon] = hit
                used.add(hit)
                break
    unmapped = [h for h in headers if h not in used]
    return mapping, unmapped


def build_mapping(input_dir, judge=None, existing=None):
    """Return {file: {"object": obj, "fields": {canonical: header}, "ignored": [...]}}."""
    files = sorted(Path(input_dir).glob("*.csv"))
    if not files:
        raise SystemExit(f"No CSV files found in {input_dir}. Drop your CRM exports there.")
    existing = existing or {}
    mapping = {}
    for path in files:
        headers, _ = _read_csv(path)
        saved = existing.get(path.name)
        if saved and set(saved["fields"].values()) <= set(headers):
            mapping[path.name] = {**saved, "mapped_by": "saved"}
            continue
        obj = _guess_object(path, headers)
        fields, unmapped = _match_headers(obj, headers)
        missing = [c for c in FIELDS[obj] if c not in fields]
        source = "rule"
        if unmapped and missing and judge and judge.enabled:
            suggested = judge.map_headers(obj, unmapped, missing)
            for canon, header in suggested.items():
                if canon in missing and header in unmapped:
                    fields[canon] = header
                    unmapped.remove(header)
            source = "rule+claude"
        mapping[path.name] = {"object": obj, "fields": fields, "ignored": unmapped, "mapped_by": source}
    return mapping


def load(input_dir, mapping):
    """Load every file into canonical records. Each record keeps its raw row for re-export."""
    data = {"accounts": [], "contacts": [], "deals": []}
    raw_headers = {}
    for fname, spec in mapping.items():
        obj = spec["object"]
        headers, rows = _read_csv(Path(input_dir) / fname)
        raw_headers[obj] = {"file": fname, "headers": headers, "fields": spec["fields"]}
        for i, row in enumerate(rows):
            rec = {canon: (row.get(h) or "").strip() for canon, h in spec["fields"].items()}
            for canon in FIELDS[obj]:
                rec.setdefault(canon, "")
            if not rec["id"]:
                rec["id"] = f"{obj[:3]}-row{i + 2}"
            rec["_raw"] = row
            data[obj].append(rec)
    return data, raw_headers


def save_mapping(mapping, path):
    Path(path).write_text(json.dumps(mapping, indent=2))


def read_mapping(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None
