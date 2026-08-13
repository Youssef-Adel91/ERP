import sys
import re

def modify_migration(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    wrappers = """
    # --- DEFENSIVE MIGRATION WRAPPERS ---
    from sqlalchemy.engine.reflection import Inspector
    bind = op.get_bind()
    from alembic import context as alembic_context
    from alembic import op as alembic_op
    current_schema = alembic_context.get_context().version_table_schema

    # Cache tables, columns, and indexes to avoid N+1 queries to the DB
    _existing_tables = set()
    _existing_columns = set()
    _existing_indexes = set()

    _res_tables = bind.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": current_schema})
    for row in _res_tables:
        _existing_tables.add(row[0])

    _res_cols = bind.execute(sa.text("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = :s"), {"s": current_schema})
    for row in _res_cols:
        _existing_columns.add((row[0], row[1]))

    _res_idx = bind.execute(sa.text("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = :s AND c.relkind = 'i'"), {"s": current_schema})
    for row in _res_idx:
        _existing_indexes.add(row[0])

    def _table_exists(table_name: str) -> bool:
        return table_name in _existing_tables

    def _index_exists(index_name: str) -> bool:
        return index_name in _existing_indexes
        
    def _column_exists(table_name: str, column_name: str) -> bool:
        return (table_name, column_name) in _existing_columns

    def _safe_create_table(name, *args, **kwargs):
        if not _table_exists(name):
            alembic_op.create_table(name, *args, **kwargs)
            _existing_tables.add(name)

    def _safe_create_index(name, table_name, *args, **kwargs):
        if not _index_exists(name) and _table_exists(table_name):
            alembic_op.create_index(name, table_name, *args, **kwargs)
            _existing_indexes.add(name)

    def _safe_add_column(table_name, column, *args, **kwargs):
        if _table_exists(table_name) and not _column_exists(table_name, column.name):
            alembic_op.add_column(table_name, column, *args, **kwargs)
            _existing_columns.add((table_name, column.name))
    # ------------------------------------
"""

    if "# --- DEFENSIVE MIGRATION WRAPPERS ---" in content:
        content = re.sub(r'# --- DEFENSIVE MIGRATION WRAPPERS ---.*?# ------------------------------------', '', content, flags=re.DOTALL)
        content = content.replace("def upgrade() -> None:\n\n", "def upgrade() -> None:\n")

    if "# --- DEFENSIVE MIGRATION WRAPPERS ---" not in content:
        content = content.replace("def upgrade() -> None:", "def upgrade() -> None:\n" + wrappers)

    # Use negative lookbehind to avoid replacing alembic_op.
    content = re.sub(r'(?<!alembic_)\bop\.create_table\b', '_safe_create_table', content)
    content = re.sub(r'(?<!alembic_)\bop\.create_index\b', '_safe_create_index', content)
    content = re.sub(r'(?<!alembic_)\bop\.add_column\b', '_safe_add_column', content)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Successfully modified {file_path}")

if __name__ == "__main__":
    import glob
    if len(sys.argv) > 1:
        rev = sys.argv[1]
        files = glob.glob(f"alembic/tenant/versions/{rev}*.py")
    else:
        files = glob.glob("alembic/tenant/versions/*_create_missing_tables_and_columns.py")
    
    for f in files:
        modify_migration(f)
