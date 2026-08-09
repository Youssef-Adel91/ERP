import re, pathlib

versions = pathlib.Path('alembic/tenant/versions')
migrations = {}
for f in versions.glob('*.py'):
    content = f.read_text(encoding='utf-8', errors='ignore')
    rev_m = re.search(r'revision\s*[:=]\s*["\'](\w+)["\']', content)
    down_m = re.search(r'down_revision\s*[:=]\s*["\'](\w+)["\']', content)
    down_none = re.search(r'down_revision\s*[:=]\s*None', content)
    if rev_m:
        rev = rev_m.group(1)
        down = down_m.group(1) if down_m else ('None' if down_none else '?')
        migrations[rev] = {'file': f.name, 'down': down}

# Build sorted chain
print(f"{'down_revision':>20} -> {'revision':>15}  file")
print("-" * 90)
for rev, info in sorted(migrations.items(), key=lambda x: x[1]['down']):
    print(f"{info['down']:>20} -> {rev:>15}  {info['file']}")

# Find any revisions that appear as down_revision for MULTIPLE migrations (branches)
from collections import Counter
down_counts = Counter(info['down'] for info in migrations.values())
branches = {d: c for d, c in down_counts.items() if c > 1}
if branches:
    print("\n⚠️  BRANCHES DETECTED (same down_revision used by multiple migrations):")
    for down_rev, count in branches.items():
        print(f"  down_revision={down_rev} is referenced by {count} migrations:")
        for rev, info in migrations.items():
            if info['down'] == down_rev:
                print(f"    - {rev}: {info['file']}")

# Find accounting_periods creators
print("\n📋 Migrations that CREATE accounting_periods:")
for f in versions.glob('*.py'):
    content = f.read_text(encoding='utf-8', errors='ignore')
    if 'accounting_periods' in content and "create_table" in content:
        print(f"  {f.name}")
