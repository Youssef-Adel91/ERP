import re

def fix_deps(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        c = f.read()

    c = c.replace('def require_roles(*roles: str):', 'def require_roles(*roles: UserRole):')
    c = c.replace('if not any(role in current_user.roles for role in roles):', 'if current_user.role not in roles:')
    c = c.replace('from app.modules.system.models import Tenant, User', 'from app.modules.system.models import Tenant, User, UserRole')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(c)

fix_deps('app/modules/system/dependencies.py')
