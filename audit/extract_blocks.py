#!/usr/bin/env python3
"""Extract every ```llvm block from the book, with location, for triage.

We cannot auto-verify every block (many are fragments, mixed sources, or
deliberately-illustrative). But we CAN enumerate them and classify:
  - ASSEMBLABLE: parses as a complete module on its own
  - FRAGMENT:    needs surrounding context (bare instructions, partial fn)
"""
import re, glob, os, subprocess, sys, json

def blocks(path):
    src = open(path).read()
    out = []
    for m in re.finditer(r'```llvm\n(.*?)```', src, re.S):
        body = m.group(1)
        line = src[:m.start()].count('\n') + 1
        out.append((path, line, body))
    return out

all_blocks = []
for f in sorted(glob.glob('book/*.md')):
    all_blocks.extend(blocks(f))

print(f"total llvm blocks: {len(all_blocks)}")
os.makedirs('review_scratch/blocks', exist_ok=True)
assembleable = 0
results = []
for i, (path, line, body) in enumerate(all_blocks):
    fn = f"review_scratch/blocks/b{i:03d}.ll"
    open(fn, 'w').write(body)
    r = subprocess.run(['llvm-as-18', fn, '-o', '/dev/null'],
                       capture_output=True, text=True)
    ok = r.returncode == 0
    # a block that contains a `define`/`declare`/`@` and assembles is a full module
    looks_module = bool(re.search(r'^\s*(define|declare|@|%[A-Za-z_].*= type|target )', body, re.M))
    if ok and looks_module:
        assembleable += 1
    results.append(dict(i=i, file=os.path.basename(path), line=line,
                        parses=ok, looks_module=looks_module,
                        err=r.stderr.strip().splitlines()[0] if r.stderr.strip() else ""))
json.dump(results, open('review_scratch/blocks/index.json','w'), ensure_ascii=False, indent=1)
print(f"blocks that parse standalone: {sum(1 for r in results if r['parses'])}")
print(f"blocks that parse AND look like full modules: {assembleable}")
print("\nFirst 20 that look like modules but FAIL to parse (highest-priority triage):")
n=0
for r in results:
    if r['looks_module'] and not r['parses']:
        print(f"  {r['file']}:{r['line']}  {r['err']}")
        n+=1
        if n>=20: break
if n==0: print("  (none)")
