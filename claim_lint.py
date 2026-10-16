#!/usr/bin/env python3
"""claim-lint: check outward copy against a table of claims you must not make.

You keep a rules file (a Markdown table or YAML) listing claims you have retracted or are not
allowed to make, with the reason and a safe alternative. claim-lint reads a draft (a file, a
folder of files, or stdin) and reports every line that uses one of those claims.

Exit codes: 0 = clean, 1 = at least one banned claim found, 2 = usage or rules-file error.

    claim-lint --rules rules.md --file draft.md
    claim-lint --rules rules.md --file site/          # every text file in a folder
    cat email.txt | claim-lint --rules rules.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable, Iterator, List, Optional, Sequence, TextIO

__version__ = "1.0.0"

TEXT_EXT = {".md", ".markdown", ".txt", ".html", ".htm", ".astro", ".mdx", ".rst", ".csv", ".json", ".yml", ".yaml"}
HTML_EXT = {".html", ".htm", ".astro", ".md", ".mdx"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
IGNORE_MARKER = re.compile(r"claim-lint:\s*ignore", re.IGNORECASE)
SEPARATOR_ROW = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")

# Header names accepted for each column (lower case). The first matching header wins.
COLUMN_NAMES = {
    "pattern": ("pattern", "claim", "banned claim", "phrase", "regex"),
    "why": ("why", "reason", "why banned", "why it's banned", "source"),
    "instead": ("instead", "safe alternative", "say instead", "alternative", "use instead"),
    "org": ("org", "organisation", "organization", "scope", "brand"),
    "label": ("label", "id", "name"),
}


class RulesError(Exception):
    """The rules file could not be read or is malformed."""


@dataclass
class Rule:
    pattern: str
    why: str = ""
    instead: str = ""
    org: str = ""
    label: str = ""
    regex: re.Pattern = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.regex = compile_pattern(self.pattern)
        if not self.label:
            p = self.pattern.strip()
            if len(p) > 2 and p.startswith("/") and p.endswith("/"):
                p = p[1:-1].replace(r"\b", "")
            self.label = p[:40]


@dataclass
class Hit:
    source: str
    line: int
    label: str
    matched: str
    text: str
    why: str
    instead: str

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def compile_pattern(pattern: str) -> re.Pattern:
    """Turn a rules-file pattern into a regex.

    /.../  is a regular expression, used as written (case-insensitive).
    Anything else is a plain phrase: matched as whole words, case-insensitive, with any run of
    spaces or a line-wrap allowed between words. A phrase ending in * matches any word ending,
    so "guarantee*" matches guarantee, guaranteed and guarantees.
    """
    p = pattern.strip()
    if not p:
        raise RulesError("empty pattern")
    if len(p) > 2 and p.startswith("/") and p.endswith("/"):
        body = p[1:-1]
    else:
        words = p.split()
        parts = []
        for w in words:
            if w.endswith("*") and len(w) > 1:
                parts.append(re.escape(w[:-1]) + r"\w*")
            else:
                parts.append(re.escape(w))
        body = r"\s+".join(parts)
        if re.match(r"\w", p):
            body = r"\b" + body
        if re.search(r"[\w*]$", p):
            body = body + r"\b"
    try:
        return re.compile(body, re.IGNORECASE)
    except re.error as e:
        raise RulesError("bad pattern %r: %s" % (pattern, e)) from e


# ---------------------------------------------------------------- rules files

def _split_row(line: str) -> List[str]:
    """Split a Markdown table row into cells. A | inside `code` or written as \\| stays in the
    cell, so a regex like `/a|b/` can live in a pattern cell."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, in_code, i = [], [], False, 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur).strip())
    return cells


def _unwrap(cell: str) -> str:
    """Remove Markdown code ticks around a pattern cell: `foo` -> foo."""
    c = cell.strip()
    if len(c) >= 2 and c.startswith("`") and c.endswith("`"):
        return c[1:-1].strip()
    return c


def parse_markdown_rules(text: str) -> List[Rule]:
    """Read every Markdown table that has a pattern column. Other text is ignored, so the rules
    file can carry headings and notes for the people who maintain it."""
    rules: List[Rule] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if line.strip().startswith("|") and SEPARATOR_ROW.match(nxt):
            headers = [h.lower().strip("* ") for h in _split_row(line)]
            col = {}
            for key, names in COLUMN_NAMES.items():
                for idx, h in enumerate(headers):
                    if h in names:
                        col[key] = idx
                        break
            i += 2
            if "pattern" not in col:
                continue
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = _split_row(lines[i])

                def cell(key: str) -> str:
                    idx = col.get(key)
                    return cells[idx] if idx is not None and idx < len(cells) else ""

                pat = _unwrap(cell("pattern"))
                if pat and not pat.startswith("~~"):
                    try:
                        rules.append(Rule(pattern=pat, why=cell("why"), instead=cell("instead"),
                                          org=cell("org"), label=_unwrap(cell("label"))))
                    except RulesError as e:
                        raise RulesError("line %d: %s" % (i + 1, e)) from e
                i += 1
            continue
        i += 1
    return rules


def parse_yaml_rules(text: str) -> List[Rule]:
    try:
        import yaml  # type: ignore
    except ImportError as e:
        raise RulesError("YAML rules need PyYAML (pip install pyyaml), or use a Markdown table") from e
    data = yaml.safe_load(text)
    items = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise RulesError('YAML rules must be a list, or a mapping with a "rules" list')
    rules = []
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict) or not item.get("pattern"):
            raise RulesError("rule %d has no pattern" % n)
        rules.append(Rule(pattern=str(item["pattern"]), why=str(item.get("why", "")),
                          instead=str(item.get("instead", "")), org=str(item.get("org", "")),
                          label=str(item.get("label", ""))))
    return rules


def load_rules(path: str, org: Optional[str] = None) -> List[Rule]:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        raise RulesError("cannot read rules file %s: %s" % (path, e)) from e
    if os.path.splitext(path)[1].lower() in (".yml", ".yaml"):
        rules = parse_yaml_rules(text)
    else:
        rules = parse_markdown_rules(text)
    if not rules:
        raise RulesError("%s has no rules (expected a Markdown table with a 'pattern' column)" % path)
    if org:
        rules = [r for r in rules if not r.org or r.org.lower() in ("all", "*", org.lower())]
    return rules


# ---------------------------------------------------------------- scanning

def strip_html_comments(lines: Sequence[str]) -> List[str]:
    """Blank out <!-- ... --> so notes in comments are not read as copy. One output line per
    input line, so reported line numbers stay true."""
    out, inside = [], False
    for line in lines:
        kept, i = [], 0
        while i < len(line):
            if inside:
                end = line.find("-->", i)
                if end < 0:
                    i = len(line)
                else:
                    inside, i = False, end + 3
            else:
                start = line.find("<!--", i)
                if start < 0:
                    kept.append(line[i:])
                    i = len(line)
                else:
                    kept.append(line[i:start])
                    inside, i = True, start + 4
        out.append("".join(kept))
    return out


def scan_lines(lines: Iterable[str], rules: Sequence[Rule], source: str = "<stdin>") -> List[Hit]:
    """Check each line, and each pair of adjacent lines so a phrase wrapped across a line break
    is still found. A line containing 'claim-lint: ignore' is skipped."""
    hits: List[Hit] = []
    seen = set()
    prev = ""
    prev_ignored = True
    for n, line in enumerate(lines, 1):
        ignored = bool(IGNORE_MARKER.search(line))
        if not ignored:
            for rule in rules:
                at, text = n, line
                m = rule.regex.search(line)
                if m is None and not prev_ignored and prev.strip():
                    joined = prev.rstrip() + " " + line.lstrip()
                    wrapped = rule.regex.search(joined)
                    # Only a match that crosses the line break is new; others were found already.
                    if wrapped and wrapped.start() < len(prev.rstrip()) < wrapped.end():
                        m, at, text = wrapped, n - 1, joined
                if m is None or (at, rule.label) in seen:
                    continue
                seen.add((at, rule.label))
                hits.append(Hit(source=source, line=at, label=rule.label, matched=m.group(0),
                                text=text.strip()[:200], why=rule.why, instead=rule.instead))
        prev, prev_ignored = line, ignored
    return hits


def scan_text(text: str, rules: Sequence[Rule], source: str = "<stdin>", html: bool = False) -> List[Hit]:
    lines = text.splitlines()
    if html:
        lines = strip_html_comments(lines)
    return scan_lines(lines, rules, source)


def iter_files(paths: Sequence[str]) -> Iterator[str]:
    for p in paths:
        if os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
                for fn in sorted(filenames):
                    if os.path.splitext(fn)[1].lower() in TEXT_EXT:
                        yield os.path.join(dirpath, fn)
        else:
            yield p


def scan_paths(paths: Sequence[str], rules: Sequence[Rule], keep_comments: bool = False) -> List[Hit]:
    hits: List[Hit] = []
    for path in iter_files(paths):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            raise RulesError("cannot read %s: %s" % (path, e)) from e
        html = not keep_comments and os.path.splitext(path)[1].lower() in HTML_EXT
        hits += scan_text(text, rules, source=path, html=html)
    return hits


# ---------------------------------------------------------------- output

def render(hits: Sequence[Hit], out: TextIO) -> None:
    if not hits:
        out.write("claim-lint: clean, no banned claims found.\n")
        return
    for h in hits:
        out.write("%s:%d: [%s] \"%s\"\n" % (h.source, h.line, h.label, h.matched))
        out.write("    line:    %s\n" % h.text)
        if h.why:
            out.write("    why:     %s\n" % h.why)
        if h.instead:
            out.write("    instead: %s\n" % h.instead)
    files = len({h.source for h in hits})
    out.write("\nclaim-lint: %d banned claim(s) in %d source(s). Fix them before publishing.\n" % (len(hits), files))


def main(argv: Optional[Sequence[str]] = None, stdin: Optional[TextIO] = None, stdout: Optional[TextIO] = None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    ap = argparse.ArgumentParser(prog="claim-lint", description=__doc__.split("\n\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", required=True, help="rules file: a Markdown table (.md) or YAML (.yml)")
    ap.add_argument("--file", action="append", default=[],
                    help="file or folder to check (repeatable). Omit, or pass -, to read stdin")
    ap.add_argument("--org", help="apply only rules whose org column is empty, 'all', or this value")
    ap.add_argument("--keep-comments", action="store_true",
                    help="also check text inside HTML comments (skipped by default)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--list-rules", action="store_true", help="print the loaded rules and exit")
    ap.add_argument("--version", action="version", version="%(prog)s " + __version__)
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 2

    try:
        rules = load_rules(args.rules, args.org)
        if args.list_rules:
            for r in rules:
                stdout.write("%-40s %s\n" % (r.label, r.regex.pattern))
            return 0
        files = [f for f in args.file if f != "-"]
        hits: List[Hit] = []
        if files:
            hits += scan_paths(files, rules, args.keep_comments)
        if not files or "-" in args.file:
            hits += scan_text(stdin.read(), rules, "<stdin>", html=not args.keep_comments)
    except RulesError as e:
        sys.stderr.write("claim-lint: error: %s\n" % e)
        return 2

    if args.json:
        stdout.write(json.dumps({"hits": [h.as_dict() for h in hits], "count": len(hits)}, indent=2) + "\n")
    else:
        render(hits, stdout)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
