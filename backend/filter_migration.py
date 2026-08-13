import re

file_path = r'E:\me\Projects for me\المرجع الرقمي للتاجر المصري\ERP\backend\alembic\tenant\versions\99f91dd227cd_add_missing_tenant_models.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# We need to extract the upgrade and downgrade functions.
# Actually, since it's hard to parse python AST for this, let's just find the table creations.

tables_to_keep = ['case_types', 'case_vendors', 'case_resources', 'cases', 'hr_employees', 'pos_cash_shifts']

# But wait, case_types and case_vendors must be created before cases (due to foreign keys).
# Alembic usually sorts them correctly. Let's just find their op.create_table blocks.

upgrade_statements = []

for table in tables_to_keep:
    # Match op.create_table('table_name', ...) up to the closing parenthesis.
    pattern = r"(    op\.create_table\('" + table + r"',\s+.*?\n    \))"
    match = re.search(pattern, content, flags=re.DOTALL)
    if match:
        upgrade_statements.append(match.group(1))

    # Match op.create_index(...) for this table
    index_pattern = r"(    op\.create_index\([^,]+,\s*'" + table + r"',\s+\[.*?\].*?\))"
    for match in re.finditer(index_pattern, content, flags=re.DOTALL):
        upgrade_statements.append(match.group(1))

upgrade_body = '\n'.join(upgrade_statements)

if not upgrade_body:
    upgrade_body = '    pass'

new_content = f'''\"\"\"add_missing_tenant_models

Revision ID: 99f91dd227cd
Revises: l2g7h8i9j0k1
Create Date: 2026-08-11 00:06:00.000000

\"\"\"
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '99f91dd227cd'
down_revision = 'l2g7h8i9j0k1'
branch_labels = None
depends_on = None

def upgrade() -> None:
{upgrade_body}

def downgrade() -> None:
    pass
'''

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Filtered successfully.')
