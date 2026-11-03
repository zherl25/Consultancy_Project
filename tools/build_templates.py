"""Build the master template library from a past client's documentation set.

    py tools/build_templates.py data/templates/build_spec.json

The spec (kept in data/, outside git, because it quotes real client details)
names the source documents and the client-specific text in them. Every source
file is copied into data/templates/master/ with that text swapped for tokens
(see backend/generator/fill.py), and data/templates/manifest.json lists the
result for the generator.

Spec outline:
{
  "output": "data/templates",
  "sources": {"lth": "<folder>", ...},
  "rules": {"lth": {"replace": [[regex, replacement, "i"?], ...],
                    "codes":   {"QP-01": "qp_document_control", ...}}},
  "check_words": ["LTH", ...],               # must not survive in any master
  "templates": [{"key", "source", "file", "kind", "title", "module", "order",
                 "code"?, "parent"?, "edits"?: [...]}]
}

Edits run before the rules and act on paragraphs whose text matches "match":
  prefix / prefix_heading (nearest earlier paragraph matching "heading") / set / delete / insert_after (text or list of texts) / insert_row_after
  (cells) / transplant (copy paragraphs from another source file) /
  strip_images (remove pictures from headers & footers; optional "logo": true
  puts {{logo}} where the first one was).
"""

import json
import re
import sys
import zipfile
from copy import deepcopy
from pathlib import Path

import openpyxl
from docx import Document
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.generator import ooxml  # noqa: E402

_DRAWINGS = (qn("w:drawing"), qn("w:pict"), "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent")


def _rules(spec: dict, source: str, self_key: str = "") -> list[tuple[re.Pattern, str]]:
    """Replacement rules for a source; "@self" in a replacement means the template's own key."""
    rules = spec["rules"].get(source, {})
    out = [(re.compile(r[0], re.I if len(r) > 2 and "i" in r[2] else 0), r[1].replace("@self", self_key))
           for r in rules.get("replace", [])]
    codes = rules.get("codes", {})
    if codes:
        alts = "|".join(re.escape(c) for c in sorted(codes, key=len, reverse=True))
        pat = re.compile(r"(?<![A-Za-z0-9-])(" + alts + r")(?![A-Za-z0-9])")
        out.append((pat, lambda m: "{{ref:" + codes[m.group(1)] + "}}"))
    return out


def _apply_rules(text_or_p, rules, is_para=True):
    if is_para:
        for pat, repl in rules:
            ooxml.sub_paragraph(text_or_p, pat, repl)
        return None
    s = text_or_p
    for pat, repl in rules:
        s = pat.sub(repl, s)
    return s


def _paragraphs(doc):
    for root, _ in ooxml.stories(doc):
        yield from list(root.iter(ooxml.W_P))


def _find(doc, pattern: str):
    pat = re.compile(pattern)
    return [p for p in _paragraphs(doc) if pat.search(ooxml.para_text(p).strip())]


def _clone_para(p, text: str):
    new = deepcopy(p)
    for child in list(new):          # drop nested drawings / text boxes in the copy
        if child.tag == qn("w:r") and any(c.tag in _DRAWINGS for c in child):
            new.remove(child)
    ooxml.set_text(new, text)
    return new


def _transplant(spec, edit, target_doc, anchor):
    src_doc = Document(str(Path(spec["sources"][edit["from_source"]]) / edit["from_file"]))
    body = src_doc.element.body
    start, end = re.compile(edit["start"]), re.compile(edit["end"])
    picked, inside = [], False
    for el in list(body):
        text = ooxml.para_text(el).strip() if el.tag == ooxml.W_P else ""
        if not inside:
            inside = bool(el.tag == ooxml.W_P and start.search(text))
            continue
        if el.tag == ooxml.W_P and end.search(text):
            break
        picked.append(el)
    if not picked:
        raise SystemExit(f"transplant found nothing between {edit['start']!r} and {edit['end']!r}")
    rules = _rules(spec, edit["from_source"])
    after = anchor
    for el in picked:
        if el.xpath(".//@r:id | .//@r:embed"):
            print(f"  ! transplanted element has a relationship (image/link) — skipped: "
                  f"{ooxml.para_text(el)[:60]!r}")
            continue
        new = deepcopy(el)
        for p in ([new] if new.tag == ooxml.W_P else list(new.iter(ooxml.W_P))):
            for drop in edit.get("drop", []):
                if re.search(drop, ooxml.para_text(p)):
                    ooxml.remove_paragraph(p)
                    break
            else:
                _apply_rules(p, rules)
                ooxml.prepend(p, edit.get("prefix", ""))   # blank lines too, so none are left behind
        after.addnext(new)
        after = new
    return len(picked)


def _strip_images(doc, edit) -> None:
    logo_done = not edit.get("logo")
    for root, part in list(ooxml.stories(doc))[1:]:
        for r in list(root.iter(qn("w:r"))):
            if any(c.tag in _DRAWINGS for c in r):
                p = ooxml.ancestor(r, ooxml.W_P)
                ooxml.remove(r)
                if not logo_done and p is not None:
                    ooxml.prepend(p, "{{logo}}")
                    logo_done = True


def _edit_docx(spec, doc, edits) -> None:
    for e in edits:
        op = e["op"]
        if op == "strip_images":
            _strip_images(doc, e)
            continue
        found = _find(doc, e["match"])
        if not found:
            raise SystemExit(f"edit {op} matched nothing: {e['match']!r}")
        if e.get("first"):
            found = found[:1]
        for p in found:
            if op == "prefix":
                ooxml.prepend(p, e["text"])
            elif op == "set":
                ooxml.set_text(p, e["text"])
            elif op == "delete":
                ooxml.remove_paragraph(p)
            elif op == "insert_after":
                after = p
                for text in ([e["text"]] if isinstance(e["text"], str) else e["text"]):
                    new = _clone_para(p, text)
                    after.addnext(new)
                    after = new
            elif op == "insert_row_after":
                row = ooxml.ancestor(p, ooxml.W_TR)
                new = deepcopy(row)
                for tc, text in zip(new.findall(ooxml.W_TC), e["cells"]):
                    paras = tc.findall(ooxml.W_P)
                    ooxml.set_text(paras[0], text)
                    for extra in paras[1:]:
                        tc.remove(extra)
                row.addnext(new)
            elif op == "prefix_heading":
                # Prefix the nearest earlier paragraph matching "heading" (e.g. a reference block title)
                heading = re.compile(e["heading"])
                prev = p.getprevious()
                while prev is not None and not (prev.tag == ooxml.W_P and heading.search(ooxml.para_text(prev))):
                    prev = prev.getprevious()
                if prev is None:
                    raise SystemExit(f"no heading {e['heading']!r} before {e['match']!r}")
                ooxml.prepend(prev, e["text"])
            elif op == "transplant":
                n = _transplant(spec, e, doc, p)
                print(f"  transplanted {n} elements")
            else:
                raise SystemExit(f"unknown edit op {op}")


def _clean_props(doc, title: str) -> None:
    cp = doc.core_properties
    cp.author = cp.last_modified_by = ""
    cp.title, cp.subject, cp.keywords, cp.comments, cp.category = title, "", "", "", ""


def _strip_app_company(path: Path) -> None:
    """Remove the <Company> entry Office writes into docProps/app.xml."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/app.xml":
                data = re.sub(rb"<Company>.*?</Company>", b"<Company></Company>", data, flags=re.S)
                data = re.sub(rb"<Manager>.*?</Manager>", b"<Manager></Manager>", data, flags=re.S)
            zout.writestr(item, data)
    tmp.replace(path)


def build_docx(spec, t, src: Path, dst: Path) -> None:
    doc = Document(str(src))
    _edit_docx(spec, doc, t.get("edits", []))
    rules = _rules(spec, t["source"], t["key"])
    for p in _paragraphs(doc):
        _apply_rules(p, rules)
    if t.get("logo", True) and not any("{{logo}}" in ooxml.para_text(p) for p in _paragraphs(doc)):
        first = next((p for p in _paragraphs(doc) if "{{company_name" in ooxml.para_text(p)), None)
        if first is not None:
            ooxml.prepend(first, "{{logo}}")
    _clean_props(doc, t["title"])
    doc.save(str(dst))


def build_xlsx(spec, t, src: Path, dst: Path) -> None:
    wb = openpyxl.load_workbook(str(src))
    rules = _rules(spec, t["source"], t["key"])
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    c.value = _apply_rules(c.value, rules, is_para=False)
        for hf in (ws.oddHeader, ws.oddFooter, ws.evenHeader, ws.evenFooter, ws.firstHeader, ws.firstFooter):
            for side in (hf.left, hf.center, hf.right):
                if side.text:
                    side.text = _apply_rules(side.text, rules, is_para=False)
        for e in t.get("cells", []):            # explicit cell edits: {"sheet", "cell", "value"}
            if e.get("sheet", ws.title) == ws.title:
                ws[e["cell"]].value = e["value"]
    wb.properties.creator = wb.properties.lastModifiedBy = ""
    wb.properties.title = t["title"]
    wb.save(str(dst))


def _all_text(path: Path) -> str:
    if path.suffix == ".xlsx":
        wb = openpyxl.load_workbook(str(path))
        parts = []
        for ws in wb.worksheets:
            parts += [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
            for hf in (ws.oddHeader, ws.oddFooter, ws.firstHeader, ws.firstFooter):
                parts += [s.text or "" for s in (hf.left, hf.center, hf.right)]
        return "\n".join(parts)
    with zipfile.ZipFile(path) as z:
        xml = " ".join(z.read(n).decode("utf8", "ignore") for n in z.namelist()
                       if n.startswith("word/") and n.endswith(".xml") or n.startswith("docProps/"))
    doc = Document(str(path))
    return "\n".join(ooxml.para_text(p) for p in _paragraphs(doc)) + "\n" + re.sub(r"<[^>]+>", " ", xml)


def main(spec_path: str) -> None:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = ROOT / spec.get("output", "data/templates")
    master = out / "master"
    master.mkdir(parents=True, exist_ok=True)
    for old in master.glob("*.*"):
        old.unlink()

    manifest, problems = [], []
    check = re.compile(r"\b(" + "|".join(spec.get("check_words", [])) + r")\b", re.I) if spec.get("check_words") else None
    leftover_code = re.compile(r"(?<![\w{:-])([A-Z]{0,2}[PFM]-[A-Z]*-?\d{2}|[A-Z]{2}\d{2}-[A-Z]{2,4})(?![\w-])")
    for t in spec["templates"]:
        src = Path(spec["sources"][t["source"]]) / t["file"]
        ext = src.suffix.lower()
        dst = master / f"{t['key']}{ext}"
        print(f"{t['key']:<28} <- {t['source']}: {t['file']}")
        (build_xlsx if ext == ".xlsx" else build_docx)(spec, t, src, dst)
        if ext == ".docx":
            _strip_app_company(dst)

        text = _all_text(dst)
        if check and (hits := sorted({m.group(0) for m in check.finditer(text)})):
            problems.append(f"{t['key']}: client text left: {hits}")
        allowed = {"QM-01", "M-01"}   # "QM-01" split across runs reads as "Q M-01" in raw XML
        if hits := sorted({m.group(0) for m in leftover_code.finditer(text)} - allowed):
            problems.append(f"{t['key']}: unmapped document codes: {hits}")
        unknown = {m for m in re.findall(r"\{\{ref:(\w+)\}\}", text)} - {x["key"] for x in spec["templates"]}
        if unknown:
            problems.append(f"{t['key']}: references to templates not in the library: {sorted(unknown)}")

        manifest.append({k: t[k] for k in ("key", "kind", "title", "module", "order", "code", "parent", "group")
                         if k in t} | {"file": dst.name})

    (out / "manifest.json").write_text(json.dumps({"templates": manifest}, indent=2), encoding="utf-8")
    print(f"\n{len(manifest)} masters written to {master}")
    if problems:
        print("\nCHECK THESE:")
        for p in problems:
            print("  -", p)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data/templates/build_spec.json"))
