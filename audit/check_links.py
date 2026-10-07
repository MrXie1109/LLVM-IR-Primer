#!/usr/bin/env python3
"""Validate every relative link and heading anchor in the book."""
import re, os, glob, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = sys.argv[1] if len(sys.argv) > 1 else "book-zh"
os.chdir(os.path.join(ROOT, TARGET))

def slug(h):
    s = h.strip().lower()
    s = re.sub(r'[^\w\s\u4e00-\u9fff-]', '', s)
    return re.sub(r'\s+', '-', s)

anchors = {f: {slug(h) for h in re.findall(r'^#{1,6}\s+(.+)$', open(f).read(), re.M)}
           for f in glob.glob('*.md')}

bad, total = [], 0
for f in glob.glob('*.md'):
    for _text, target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', open(f).read()):
        if target.startswith(('http', 'mailto')): continue
        total += 1
        path = target.split('#')[0]
        anchor = target.split('#')[1] if '#' in target else None
        if path and not os.path.exists(path):
            bad.append((f, target, 'file missing'))
        elif anchor and anchor not in anchors.get(path or f, set()):
            bad.append((f, target, 'anchor missing'))

print(f"[{TARGET}] checked {total} links across {len(anchors)} files")
for b in bad: print("  BROKEN:", b)
if bad: sys.exit(1)
print("ALL LINKS AND ANCHORS RESOLVE")
