"""Turn a client's questionnaire answers into a numbered, filled documentation set."""

import json
import re
import shutil
import zipfile
from datetime import date
from pathlib import Path

from ..db import DB_PATH
from . import catalog
from .fill import FillContext, fill

DATA_DIR      = DB_PATH.parent
TEMPLATES_DIR = DATA_DIR / "templates"
MASTER_DIR    = TEMPLATES_DIR / "master"
MANIFEST      = TEMPLATES_DIR / "manifest.json"
GENERATED_DIR = DATA_DIR / "generated"
LOGO_DIR      = DATA_DIR / "logos"

_IMAGE_TYPES = {b"\x89PNG": ".png", b"\xff\xd8\xff": ".jpg"}


class LibraryMissingError(Exception):
    """Raised when the master template library has not been built yet."""


# ── Template library ────────────────────────────────────────────────────────

def load_library() -> list[dict]:
    if not MANIFEST.exists():
        raise LibraryMissingError("The template library has not been set up yet. Please contact your consultant.")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["templates"]


def master_path(entry: dict) -> Path:
    return MASTER_DIR / entry["file"]


# ── Answers ─────────────────────────────────────────────────────────────────

def _clean(s, limit: int = 2000) -> str:
    return str(s or "").replace("\r\n", "\n").strip()[:limit]


def normalize_answers(raw: dict) -> dict:
    """Keep only known keys, with sane types and lengths."""
    out = {f["key"]: _clean(raw.get(f["key"], "")) for f in catalog.FIELDS}
    out["modules"] = [m for m in raw.get("modules", []) if m in catalog.MODULE_KEYS]
    out["policy_mode"] = "custom" if raw.get("policy_mode") == "custom" else "standard"
    out["policy_points"] = [_clean(p, 500) for p in raw.get("policy_points", [])][:20]
    out["objectives_mode"] = "custom" if raw.get("objectives_mode") == "custom" else "standard"
    cols = [c["key"] for c in catalog.OBJECTIVE_COLUMNS]
    out["objectives"] = [{c: _clean((o or {}).get(c, ""), 500) for c in cols}
                         for o in raw.get("objectives", [])][:20]
    return out


def default_answers() -> dict:
    return normalize_answers({f["key"]: f.get("default", "") for f in catalog.FIELDS})


# ── Planning: which documents, and their numbers ────────────────────────────

def plan(library: list[dict], modules: list[str]) -> list[dict]:
    """Select the templates for these modules and give each a document number and file path."""
    wanted = [t for t in library if t["module"] == "core" or t["module"] in modules]
    procedures = sorted((t for t in wanted if t["kind"] == "procedure"), key=lambda t: t["order"])
    forms = sorted((t for t in wanted if t["kind"] == "form"), key=lambda t: t["order"])
    codes = {t["key"]: f"QP-{i:02d}" for i, t in enumerate(procedures, 1)}
    codes |= {t["key"]: f"QF-{i:02d}" for i, t in enumerate(forms, 1)}

    entries = []
    for t in sorted(wanted, key=lambda t: (list(catalog.FOLDERS).index(t["kind"]), t["order"])):
        if t["kind"] == "procedure_appendix":
            if t["parent"] not in codes:
                continue
            code = f"{codes[t['parent']]} {t['code']}"
        else:
            code = codes.get(t["key"], t.get("code", ""))
        ext = Path(t["file"]).suffix
        name = _safe(f"{code} {t['title']}{ext}")
        entries.append(t | {"code": code, "path": f"{catalog.FOLDERS[t['kind']]}/{name}"})
    group = {"manual": 0, "procedure": 1, "procedure_appendix": 1, "form": 2}
    # QM-01 before its appendices; each procedure ("QP-06") before its appendix ("QP-06 Appendix 1")
    entries.sort(key=lambda e: (group[e["kind"]], e["order"] if e["kind"] == "manual" else 0, e["code"]))
    return entries


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip()


# ── Fill context ────────────────────────────────────────────────────────────

def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _dates(iso: str) -> dict[str, str]:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return {}
    return {"effective_date": d.strftime("%d/%m/%Y"), "effective_date_short": d.strftime("%d/%m/%y"),
            "effective_date_long": f"{_ordinal(d.day)} {d.strftime('%B %Y')}"}


def build_context(answers: dict, entries: list[dict], logo: bytes | None) -> FillContext:
    values = {f["key"]: answers.get(f["key"], "") for f in catalog.FIELDS}
    values |= _dates(answers.get("effective_date", ""))
    design = "design" in answers["modules"]
    values["non_applicable_clause"] = "None" if design else catalog.NOT_APPLICABLE_DESIGN

    labels = {f["key"]: f["label"] for f in catalog.FIELDS}
    labels |= {"effective_date_short": labels["effective_date"], "effective_date_long": labels["effective_date"],
               "item": "Quality policy commitment"}
    labels |= {f"item.{c['key']}": f"Quality objective – {c['label'].lower()}" for c in catalog.OBJECTIVE_COLUMNS}
    labels["item.objective"] = "Quality objective"

    conditions = set(answers["modules"])
    lists: dict[str, list] = {
        "documents": [{"code": e["code"], "title": e["title"], "date": values.get("effective_date", "")}
                      for e in entries],
    }
    if answers["policy_mode"] == "standard":
        conditions.add("standard_policy")
    else:
        points = [p for p in answers["policy_points"] if p]
        lists["policy_points"] = points or [""]          # an empty list still leaves one flagged line
    if answers["objectives_mode"] == "standard":
        conditions.add("standard_objectives")
    else:
        rows = [o for o in answers["objectives"] if any(o.values())]
        lists["objectives"] = rows or [{c["key"]: "" for c in catalog.OBJECTIVE_COLUMNS}]

    refs = {e["key"]: e["code"] for e in entries if e["kind"] != "manual"}
    return FillContext(values=values, labels=labels, conditions=conditions, refs=refs, lists=lists, logo=logo)


# ── Logo ────────────────────────────────────────────────────────────────────

def logo_path(user_id: str) -> Path | None:
    for ext in (".png", ".jpg"):
        p = LOGO_DIR / f"{user_id}{ext}"
        if p.exists():
            return p
    return None


def save_logo(user_id: str, data: bytes) -> None:
    ext = next((e for magic, e in _IMAGE_TYPES.items() if data.startswith(magic)), None)
    if not ext:
        raise ValueError("Logo must be a PNG or JPG image.")
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    delete_logo(user_id)
    (LOGO_DIR / f"{user_id}{ext}").write_bytes(data)


def delete_logo(user_id: str) -> None:
    if p := logo_path(user_id):
        p.unlink()


# ── Generation ──────────────────────────────────────────────────────────────

def generation_dir(user_id: str, generation_id: str) -> Path:
    return GENERATED_DIR / user_id / generation_id


def zip_path(user_id: str, generation_id: str) -> Path:
    return GENERATED_DIR / user_id / f"{generation_id}.zip"


def generate(user_id: str, generation_id: str, answers: dict) -> dict:
    """Fill every selected template into the generation folder and zip it. Blocking — run in a thread."""
    answers = normalize_answers(answers)
    entries = plan(load_library(), answers["modules"])
    logo = p.read_bytes() if (p := logo_path(user_id)) else None
    ctx = build_context(answers, entries, logo)

    out = generation_dir(user_id, generation_id)
    if out.exists():
        shutil.rmtree(out)
    files, all_flags = [], []
    for e in entries:
        dst = out / e["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        ctx.flags = []
        fill(master_path(e), dst, ctx)
        files.append({"path": e["path"], "code": e["code"], "title": e["title"], "flags": list(ctx.flags)})
        all_flags += [f for f in ctx.flags if f not in all_flags]

    with zipfile.ZipFile(zip_path(user_id, generation_id), "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(out / f["path"], f["path"])

    company = answers.get("company_name") or "Company"
    return {"company_name": company, "modules": answers["modules"], "files": files, "flags": all_flags,
            "zip_name": _safe(f"{company} - ISO 9001 Documentation.zip")}


def remove_generation_files(user_id: str, generation_id: str) -> None:
    shutil.rmtree(generation_dir(user_id, generation_id), ignore_errors=True)
    zip_path(user_id, generation_id).unlink(missing_ok=True)
