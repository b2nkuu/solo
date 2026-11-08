#!/usr/bin/env python3
"""Fail when inline copies in commands/*.md drift from their canonical source.

Checks (stdlib only):
  1. Marker blocks: `<!-- NAME:start ... -->` ... `<!-- NAME:end -->`. A block
     name present in more than one file must have byte-identical content.
  2. branch.pattern inline copies vs "## Appendix: branch.pattern" in
     commands/start.md (see check_branch_pattern).

Usage: check-spec-drift.py [ROOT]   (ROOT defaults to the repo root)
"""
import re
import sys
from pathlib import Path

MARKER = re.compile(r"<!--\s*([A-Za-z0-9_-]+):(start|end)\b.*?-->", re.S)


def read(path):
    return path.read_bytes().decode("utf-8")


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def collect_blocks(files, errors):
    """Return {name: [(file, content, start_line)]}."""
    blocks = {}
    for f in files:
        text = read(f)
        open_m = {}
        for m in MARKER.finditer(text):
            name, kind = m.group(1), m.group(2)
            if kind == "start":
                if name in open_m:
                    errors.append(f"{f.name}: block '{name}' has a second start marker "
                                  f"(line {line_of(text, m.start())}) before its end")
                open_m[name] = m
            else:
                s = open_m.pop(name, None)
                if s is None:
                    errors.append(f"{f.name}: end marker for '{name}' without start "
                                  f"(line {line_of(text, m.start())})")
                    continue
                blocks.setdefault(name, []).append(
                    (f.name, text[s.end():m.start()], line_of(text, s.start())))
        for name, s in open_m.items():
            errors.append(f"{f.name}: start marker for '{name}' without end "
                          f"(line {line_of(text, s.start())})")
    return blocks


def first_diff(a, b):
    la, lb = a.split("\n"), b.split("\n")
    for i in range(max(len(la), len(lb))):
        x = la[i] if i < len(la) else "<missing>"
        y = lb[i] if i < len(lb) else "<missing>"
        if x != y:
            return i + 1, x, y
    return None


def check_blocks(blocks, errors):
    for name, items in sorted(blocks.items()):
        if len({f for f, _, _ in items}) < 2:
            continue
        ref_file, ref, _ = items[0]
        for f, content, _ in items[1:]:
            if content != ref:
                n, x, y = first_diff(ref, content)
                errors.append(
                    f"block '{name}' differs between {ref_file} and {f}; "
                    f"first differing line (block-relative {n}):\n"
                    f"    {ref_file}: {x!r}\n    {f}: {y!r}")


TRANSLATION = re.compile(r"`\{prefix\}` → .*?`\{slug\}` → `[^`]*`")
SLUG_FRAGMENTS = [
    "replace each run of characters outside `[a-z0-9]` with `-`",
    "keep the longest run of whole `-`-separated words that fits in 40 "
    "(hard-cut at 40 when the first word alone is longer)",
    "use `issue`",
]


def check_branch_pattern(cmds, errors):
    start = cmds / "start.md"
    if not start.exists():
        return
    text = read(start)
    idx = text.find("## Appendix: branch.pattern")
    if idx < 0:
        errors.append("start.md: '## Appendix: branch.pattern' not found")
        return
    appendix = text[idx:]
    m = TRANSLATION.search(appendix)
    if not m:
        errors.append("start.md: regex translation sentence not found in appendix")
    else:
        for name in ("today.md", "cleanup.md"):
            p = cmds / name
            if p.exists() and m.group(0) not in read(p):
                errors.append(f"{name}: branch.pattern regex translation drifted from "
                              f"start.md appendix; expected: {m.group(0)}")
    for frag in SLUG_FRAGMENTS:
        if frag not in appendix:
            errors.append(f"start.md: branch.pattern slug rule fragment missing from appendix: {frag}")
            continue
        for name in ("fast-track.md", "loop.md"):
            p = cmds / name
            if p.exists() and frag not in read(p):
                errors.append(f"{name}: branch.pattern slug rule drifted from start.md "
                              f"appendix; missing: {frag}")


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    cmds = root / "commands"
    files = sorted(cmds.glob("*.md"))
    if not files:
        print(f"no commands/*.md under {root}", file=sys.stderr)
        return 1
    errors = []
    check_blocks(collect_blocks(files, errors), errors)
    check_branch_pattern(cmds, errors)
    if errors:
        print("spec drift detected:", file=sys.stderr)
        for e in errors:
            print(f"- {e}", file=sys.stderr)
        return 1
    print("spec drift check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
