import ast, os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."

def find_model_files():
    for dirpath, _, files in os.walk(ROOT):
        if "__pycache__" in dirpath or "alembic" in dirpath or "/tests" in dirpath or dirpath.endswith("/tests"):
            continue
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)

def get_str_enum_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases]
            if "StrEnum" in bases or "Enum" in bases:
                names.add(node.name)
    return names

def is_tenantbase_class(node):
    for b in node.bases:
        if isinstance(b, ast.Name) and b.id == "TenantBase":
            return True
    return False

def field_has_schema_tenant(call_node):
    # look for sa_column=Column(sa.Enum(..., schema="tenant" or schema=schema_name...), ...)
    src_repr = ast.dump(call_node)
    return "schema" in src_repr

results = []
for path in find_model_files():
    try:
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src, filename=path)
    except Exception:
        continue
    enum_names = get_str_enum_names(tree)
    if not enum_names:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and is_tenantbase_class(node):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_name = item.target.id
                    ann = item.annotation
                    ann_names = set()
                    for n in ast.walk(ann):
                        if isinstance(n, ast.Name):
                            ann_names.add(n.id)
                    used_enum = ann_names & enum_names
                    if not used_enum:
                        continue
                    # Check the value (Field(...) call) for sa_column with schema=
                    has_schema = False
                    if isinstance(item.value, ast.Call):
                        has_schema = field_has_schema_tenant(item.value)
                    results.append((path, node.name, field_name, sorted(used_enum), has_schema))

print(f"{'FILE':60} {'CLASS':20} {'FIELD':20} {'ENUM':20} SCHEMA_QUALIFIED")
bad = []
for path, cls, field, enum, has_schema in results:
    marker = "OK" if has_schema else "*** MISSING ***"
    if not has_schema:
        bad.append((path, cls, field, enum))
    print(f"{path:60} {cls:20} {field:20} {','.join(enum):20} {marker}")

print(f"\n\n=== {len(bad)} POTENTIALLY BUGGY (bare enum, no explicit schema) ===")
for path, cls, field, enum in bad:
    print(f"{path}: {cls}.{field} ({','.join(enum)})")
