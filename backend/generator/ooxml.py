"""Low-level helpers for editing Word XML while keeping the original formatting.

Word splits visible text into runs (w:r) of text nodes (w:t) whenever formatting,
spell-check state or edit history changes, so a phrase like "{{company_name}}"
is often spread over several nodes. These helpers work on a paragraph's text as
one string and map edits back onto the nodes underneath.
"""

import re
from copy import deepcopy
from typing import Iterator

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

W_P   = qn("w:p")
W_R   = qn("w:r")
W_T   = qn("w:t")
W_TR  = qn("w:tr")
W_TC  = qn("w:tc")
W_RPR = qn("w:rPr")
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def own_texts(p) -> list:
    """The w:t nodes of paragraph *p*, excluding those of paragraphs nested in text boxes."""
    return [t for t in p.iter(W_T) if next(t.iterancestors(W_P), None) is p]


def para_text(p) -> str:
    return "".join(t.text or "" for t in own_texts(p))


def _set(t, text: str) -> None:
    t.text = text
    t.set(_XML_SPACE, "preserve")


def replace_span(p, start: int, end: int, new: str) -> None:
    """Replace characters [start, end) of the paragraph's text with *new*.

    The new text goes into the node where the span starts, so it keeps that
    run's formatting; the rest of the span is removed from the following nodes.
    """
    pos = 0
    placed = False
    for t in own_texts(p):
        text = t.text or ""
        t_start, t_end = pos, pos + len(text)
        pos = t_end
        if not placed:
            # The span starts in this node (an empty span may also start at its very end)
            if t_start <= start and (start < t_end or start == end == t_end):
                a, b = start - t_start, min(end, t_end) - t_start
                _set(t, text[:a] + new + text[b:])
                placed = True
        elif t_start < end:
            _set(t, text[min(end, t_end) - t_start:])
        else:
            break


def sub_paragraph(p, pattern: re.Pattern, repl) -> int:
    """Regex-substitute within a paragraph's text across node boundaries. Returns the match count."""
    matches = list(pattern.finditer(para_text(p)))
    for m in reversed(matches):
        replace_span(p, m.start(), m.end(), repl(m) if callable(repl) else m.expand(repl))
    return len(matches)


def prepend(p, text: str) -> None:
    ts = own_texts(p)
    if ts:
        _set(ts[0], text + (ts[0].text or ""))
    else:
        r = OxmlElement("w:r")
        t = OxmlElement("w:t")
        _set(t, text)
        r.append(t)
        p.append(r)


def set_text(p, text: str) -> None:
    """Replace the paragraph's whole text, keeping the first run's formatting."""
    ts = own_texts(p)
    if not ts:
        prepend(p, text)
        return
    _set(ts[0], text)
    for t in ts[1:]:
        _set(t, "")


def isolate(p, start: int, end: int):
    """Move characters [start, end) of the paragraph into a run of their own and return it.

    The span must lie inside a single w:t (callers merge it first with replace_span).
    The new run copies the original run's formatting.
    """
    pos = 0
    for t in own_texts(p):
        text = t.text or ""
        if pos <= start and end <= pos + len(text):
            a, b = start - pos, end - pos
            break
        pos += len(text)
    else:
        raise ValueError("span is not inside one text node")

    r = t.getparent()
    if r.tag != W_R:
        raise ValueError("text node is not inside a run")
    rpr = r.find(W_RPR)
    content = [c for c in r if c.tag != W_RPR]
    idx = content.index(t)

    def make_run(children):
        nr = OxmlElement("w:r")
        if rpr is not None:
            nr.append(deepcopy(rpr))
        for c in children:
            nr.append(c)
        return nr

    def make_t(s):
        nt = OxmlElement("w:t")
        _set(nt, s)
        return nt

    before = content[:idx] + ([make_t(text[:a])] if text[:a] else [])
    after = ([make_t(text[b:])] if text[b:] else []) + content[idx + 1:]
    middle = make_run([make_t(text[a:b])])

    new_runs = ([make_run(before)] if before else []) + [middle] + ([make_run(after)] if after else [])
    parent = r.getparent()
    i = parent.index(r)
    parent.remove(r)
    for k, nr in enumerate(new_runs):
        parent.insert(i + k, nr)
    return middle


def ancestor(el, tag):
    return next(el.iterancestors(tag), None)


def remove(el) -> None:
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


def remove_paragraph(p) -> None:
    """Remove a paragraph, leaving an empty one if a table cell would otherwise be invalid."""
    parent = p.getparent()
    if parent is None:
        return
    if parent.tag == W_TC and len(parent.findall(W_P)) == 1:
        for child in list(p):
            if child.tag != qn("w:pPr"):
                p.remove(child)
        return
    parent.remove(p)


def stories(document) -> Iterator[tuple]:
    """(root element, part) for the body and every distinct header and footer."""
    yield document.element.body, document.part
    seen = set()
    for rel in document.part.rels.values():
        if rel.reltype.endswith(("/header", "/footer")) and rel.target_part.partname not in seen:
            seen.add(rel.target_part.partname)
            yield rel.target_part.element, rel.target_part
