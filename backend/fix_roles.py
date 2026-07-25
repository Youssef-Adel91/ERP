import re

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        c = f.read()

    # service.py & router.py
    c = c.replace('roles=["admin"]', 'role=UserRole.OWNER')
    c = c.replace('roles=data.roles', 'role=data.role')
    c = c.replace('roles=user.roles', 'role=user.role')
    c = c.replace('roles=admin_user.roles', 'role=admin_user.role')
    c = c.replace('roles=current_user.roles', 'role=current_user.role')
    c = c.replace('"roles": current_user.roles', '"role": current_user.role')
    c = c.replace('from app.modules.system.models import (', 'from app.modules.system.models import (\n    UserRole,')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(c)

fix_file('app/modules/system/service.py')
fix_file('app/modules/system/router.py')
