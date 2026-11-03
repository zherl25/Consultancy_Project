"""Fill master templates (.docx / .xlsx) with a company's answers.

Masters contain tokens in double braces:

    {{company_name}}            field value; {{company_name|upper}} upper-cased
    {{ref:qp_sales}}            number assigned to another document (e.g. "QP-07");
                                the paragraph is dropped if that document is not generated
    {{if:design}} {{if:!design}}  keep the paragraph only when the condition holds
                                ("a|b" = either, "a,b" = both)
    {{row-if:cond}}             same, but drops the whole table row
    {{repeat:list}}             repeat the paragraph once per list item ({{item}})
    {{repeat-row:list}}         repeat the table row once per item ({{item.key}})
    {{logo}}                    the company logo, or nothing when none was uploaded

A field without an answer is never guessed: it becomes a yellow-highlighted
"[TO BE CONFIRMED: <label>]" and is reported back so the client can follow up.
"""

import io
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Cm
from docx.text.run import Run
from openpyxl.styles import PatternFill

from . import ooxml

TOKEN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_CONDITIONAL = ("if:", "row-if:", "ref:")


@dataclass
class FillContext:
    values: dict[str, str]                  # field -> answer ("" or absent = unknown)
    labels: dict[str, str]                  # field -> label used when flagging
    conditions: set[str]                    # modules / switches that are on
    refs: dict[str, str]                    # template key -> assigned code, for generated docs only
    lists: dict[str, list] = field(default_factory=dict)
    logo: bytes | None = None
    flags: list[str] = field(default_factory=list)

    def flag_text(self, name: str) -> str:
        label = self.labels.get(name) or name.replace("_", " ").capitalize()
        if label not in self.flags:
            self.flags.append(label)
        return f"[TO BE CONFIRMED: {label}]"

    def condition(self, expr: str) -> bool:
        """"a,b" means a AND b; "a|b" means a OR b; "!a" negates."""
        def atom(a: str) -> bool:
            return (a.lstrip("!") in self.conditions) != a.startswith("!")
        return all(any(atom(a) for a in part.split("|")) for part in expr.split(","))

    def resolve(self, token: str) -> tuple[str, bool]:
        """Return (text, is_flagged) for a field or reference token."""
        if token.startswith("ref:"):
            return self.refs[token[4:]], False
        name, _, fmt = token.partition("|")
        value = (self.values.get(name) or "").strip()
        if not value:
            return self.flag_text(name), True
        return (value.upper() if fmt == "upper" else value), False


# ── Word ─────────────────────────────────────────────────────────────────────

class _PartHolder:
    """Lets python-docx's Run.add_picture find the part (body/header) it lives in."""
    def __init__(self, part):
        self.part = part


def _item_fields(ctx: FillContext, prefix: str, item) -> dict[str, str]:
    """Register a repeat item's values as temporary fields; returns token -> field name."""
    mapping = {}
    if isinstance(item, dict):
        for key, val in item.items():
            name = f"{prefix}_{key}"
            ctx.values[name] = val or ""
            ctx.labels.setdefault(name, ctx.labels.get(f"item.{key}", key.replace("_", " ").capitalize()))
            mapping[f"item.{key}"] = name
    else:
        ctx.values[prefix] = item or ""
        ctx.labels.setdefault(prefix, ctx.labels.get("item", "List item"))
        mapping["item"] = prefix
    return mapping


def _rewrite_item_tokens(el, mapping: dict[str, str], repeat_token: re.Pattern) -> None:
    for p in el.iter(ooxml.W_P):
        ooxml.sub_paragraph(p, repeat_token, "")
        ooxml.sub_paragraph(p, TOKEN, lambda m: "{{" + mapping[m.group(1)] + "}}"
                            if m.group(1) in mapping else m.group(0))


def _expand_repeats(root, ctx: FillContext) -> None:
    counter = 0
    for kind, tag in (("repeat-row", ooxml.W_TR), ("repeat", ooxml.W_P)):
        pattern = re.compile(r"\{\{\s*" + kind + r":([\w.]+)\s*\}\}")
        for p in list(root.iter(ooxml.W_P)):
            m = pattern.search(ooxml.para_text(p))
            if not m:
                continue
            el = p if tag == ooxml.W_P else ooxml.ancestor(p, ooxml.W_TR)
            if el is None or el.getparent() is None:
                continue
            for item in ctx.lists.get(m.group(1), []):
                counter += 1
                clone = deepcopy(el)
                _rewrite_item_tokens(clone, _item_fields(ctx, f"__r{counter}", item),
                                     re.compile(r"\{\{\s*" + kind + r":[\w.]+\s*\}\}"))
                el.addprevious(clone)
            ooxml.remove(el)


def _apply_conditions(root, ctx: FillContext) -> None:
    for p in list(root.iter(ooxml.W_P)):
        if p.getparent() is None:
            continue
        tokens = [m.group(1) for m in TOKEN.finditer(ooxml.para_text(p))]
        drop_row = drop_para = False
        for tok in tokens:
            if tok.startswith("row-if:") and not ctx.condition(tok[7:]):
                drop_row = True
            elif tok.startswith("if:") and not ctx.condition(tok[3:]):
                drop_para = True
            elif tok.startswith("ref:") and tok[4:] not in ctx.refs:
                drop_para = True
        if drop_row and (row := ooxml.ancestor(p, ooxml.W_TR)) is not None:
            ooxml.remove(row)
        elif drop_row or drop_para:
            ooxml.remove_paragraph(p)
        else:
            ooxml.sub_paragraph(p, re.compile(r"\{\{\s*(?:row-)?if:[^{}]*\}\}"), "")


def _fill_values(root, part, ctx: FillContext) -> None:
    for p in list(root.iter(ooxml.W_P)):
        matches = list(TOKEN.finditer(ooxml.para_text(p)))
        for m in reversed(matches):
            token = m.group(1)
            if token == "logo":
                _place_logo(p, m, part, ctx)
                continue
            text, flagged = ctx.resolve(token)
            if not flagged and "\n" not in text:
                ooxml.replace_span(p, m.start(), m.end(), text)
                continue
            # Needs a run of its own: for the highlight or for line breaks
            ooxml.replace_span(p, m.start(), m.end(), m.group(0))
            r = ooxml.isolate(p, m.start(), m.end())
            for t in r.findall(ooxml.W_T):
                r.remove(t)
            for i, line in enumerate(text.split("\n")):
                if i:
                    r.add_br()
                r.add_t(line)
            if flagged:
                r.get_or_add_rPr().highlight_val = WD_COLOR_INDEX.YELLOW


def _place_logo(p, m, part, ctx: FillContext) -> None:
    if not ctx.logo:
        ooxml.replace_span(p, m.start(), m.end(), "")
        return
    ooxml.replace_span(p, m.start(), m.end(), m.group(0))
    r = ooxml.isolate(p, m.start(), m.end())
    for t in r.findall(ooxml.W_T):
        r.remove(t)
    Run(r, _PartHolder(part)).add_picture(io.BytesIO(ctx.logo), height=Cm(1.4))
    r.add_t("  ")                    # keep the logo off the text that follows


def fill_docx(src: Path, dst: Path, ctx: FillContext) -> None:
    doc = Document(str(src))
    for root, part in ooxml.stories(doc):
        _expand_repeats(root, ctx)
        _apply_conditions(root, ctx)
        _fill_values(root, part, ctx)
    doc.save(str(dst))


# ── Excel ────────────────────────────────────────────────────────────────────

_YELLOW = PatternFill("solid", start_color="FFFF00", end_color="FFFF00")


def _fill_string(s: str, ctx: FillContext) -> tuple[str | None, bool]:
    """Fill one cell / header string. Returns (new text or None to clear, any flagged)."""
    flagged = False

    def repl(m):
        nonlocal flagged
        tok = m.group(1)
        if tok.startswith(("if:", "row-if:")) or tok == "logo":
            return ""
        text, f = ctx.resolve(tok)
        flagged |= f
        return text

    for tok in (m.group(1) for m in TOKEN.finditer(s)):
        if tok.startswith(_CONDITIONAL):
            kind, _, arg = tok.partition(":")
            if (kind == "ref" and arg not in ctx.refs) or (kind != "ref" and not ctx.condition(arg)):
                return None, False
    return TOKEN.sub(repl, s), flagged


def fill_xlsx(src: Path, dst: Path, ctx: FillContext) -> None:
    wb = openpyxl.load_workbook(str(src))
    repeat = re.compile(r"\{\{\s*repeat-row:([\w.]+)\s*\}\}")
    for ws in wb.worksheets:
        # Repeated rows write downwards into the form's existing (pre-formatted) rows
        for row in list(ws.iter_rows()):
            texts = [c.value for c in row if isinstance(c.value, str)]
            m = next((repeat.search(t) for t in texts if repeat.search(t)), None)
            if not m:
                continue
            items = ctx.lists.get(m.group(1), [])
            templates = {c.column: c.value for c in row if isinstance(c.value, str) and "{{" in c.value}
            for col, tpl in templates.items():
                ws.cell(row=row[0].row, column=col).value = None
            for i, item in enumerate(items):
                for col, tpl in templates.items():
                    tpl = repeat.sub("", tpl)
                    val = TOKEN.sub(lambda mm: str((item.get(mm.group(1)[5:], "") if isinstance(item, dict)
                                                    else item) if mm.group(1).startswith("item") else mm.group(0)),
                                    tpl)
                    ws.cell(row=row[0].row + i, column=col).value = val
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and "{{" in c.value:
                    text, flagged = _fill_string(c.value, ctx)
                    c.value = text
                    if flagged:
                        c.fill = _YELLOW
        for hf in (ws.oddHeader, ws.oddFooter, ws.evenHeader, ws.evenFooter, ws.firstHeader, ws.firstFooter):
            for side in (hf.left, hf.center, hf.right):
                if side.text and "{{" in side.text:
                    side.text = _fill_string(side.text, ctx)[0] or ""
    wb.save(str(dst))


def fill(src: Path, dst: Path, ctx: FillContext) -> None:
    if src.suffix.lower() == ".xlsx":
        fill_xlsx(src, dst, ctx)
    else:
        fill_docx(src, dst, ctx)
