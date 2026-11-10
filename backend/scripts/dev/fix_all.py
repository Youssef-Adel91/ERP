import glob
import os


def fix_all():
    for f in glob.glob('app/modules/**/*.py', recursive=True) + glob.glob('app/plugins/**/*.py', recursive=True):
        if not os.path.isfile(f): continue
        with open(f, encoding='utf-8') as file:
            c = file.read()
            
        modified = False
        
        # 1. Remove from __future__ import annotations
        if 'from __future__ import annotations' in c:
            c = c.replace('from __future__ import annotations\n', '')
            modified = True
            
        # 2. Fix timezone awareness
        if 'datetime.now(timezone.utc)' in c:
            c = c.replace('datetime.now(timezone.utc)', 'datetime.now(timezone.utc).replace(tzinfo=None)')
            modified = True
            
        if modified:
            with open(f, 'w', encoding='utf-8') as file:
                file.write(c)
                
    # 3. Fix UserRole in system/models.py
    sm = 'app/modules/system/models.py'
    if os.path.exists(sm):
        with open(sm, encoding='utf-8') as file:
            c = file.read()
        
        if 'UserRole' not in c:
            c = c.replace('from sqlalchemy import JSON, Index, String, UniqueConstraint, text', 'from sqlalchemy import JSON, Index, String, UniqueConstraint, text\nimport sqlalchemy as sa\nfrom enum import StrEnum')
            
            role_enum = '''
class UserRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    STAFF = "STAFF"
    SALES = "SALES"
    ACCOUNTING = "ACCOUNTING"
'''
            c = c.replace('class User(SQLModel, table=True):', role_enum + '\nclass User(SQLModel, table=True):')
            c = c.replace('roles: list[str] = Field(default_factory=lambda: ["staff"], sa_type=JSON)', 'role: UserRole = Field(default=UserRole.OWNER, sa_type=sa.String(20))')
            
            with open(sm, 'w', encoding='utf-8') as file:
                file.write(c)

    # 4. Fix schemas.py
    ss = 'app/modules/system/schemas.py'
    if os.path.exists(ss):
        with open(ss, encoding='utf-8') as file:
            c = file.read()
        
        if 'UserRole' not in c:
            c = c.replace('from app.modules.system.models import PlanTier, TenantStatus', 'from app.modules.system.models import PlanTier, TenantStatus, UserRole')
            c = c.replace('roles: list[str] = Field(default_factory=lambda: ["staff"])', 'role: UserRole = Field(default=UserRole.STAFF)')
            c = c.replace('roles: list[str] | None = None', 'role: UserRole | None = None')
            c = c.replace('roles: list[str]', 'role: UserRole')
            
            with open(ss, 'w', encoding='utf-8') as file:
                file.write(c)

    # 5. Fix service.py
    srv = 'app/modules/system/service.py'
    if os.path.exists(srv):
        with open(srv, encoding='utf-8') as file:
            c = file.read()
            
        if 'UserRole' not in c:
            c = c.replace('roles=["admin"]', 'role=UserRole.OWNER')
            c = c.replace('roles=data.roles', 'role=data.role')
            c = c.replace('roles=user.roles', 'role=user.role')
            c = c.replace('roles=admin_user.roles', 'role=admin_user.role')
            c = c.replace('from app.modules.system.models import (', 'from app.modules.system.models import (\n    UserRole,')
            
            with open(srv, 'w', encoding='utf-8') as file:
                file.write(c)

    # 6. Fix router.py
    rt = 'app/modules/system/router.py'
    if os.path.exists(rt):
        with open(rt, encoding='utf-8') as file:
            c = file.read()
            
        if 'UserRole' not in c:
            c = c.replace('roles=["admin"]', 'role=UserRole.OWNER')
            c = c.replace('roles=data.roles', 'role=data.role')
            c = c.replace('roles=user.roles', 'role=user.role')
            c = c.replace('roles=current_user.roles', 'role=current_user.role')
            c = c.replace('"roles": current_user.roles', '"role": current_user.role')
            c = c.replace('from app.modules.system.models import Tenant, TenantStatus, User', 'from app.modules.system.models import Tenant, TenantStatus, User, UserRole')
            
            with open(rt, 'w', encoding='utf-8') as file:
                file.write(c)

    # 7. Fix dependencies.py
    dep = 'app/modules/system/dependencies.py'
    if os.path.exists(dep):
        with open(dep, encoding='utf-8') as file:
            c = file.read()
            
        if 'UserRole' not in c:
            c = c.replace('def require_roles(*roles: str):', 'def require_roles(*roles: UserRole):')
            c = c.replace('if not any(role in current_user.roles for role in roles):', 'if current_user.role not in roles:')
            c = c.replace('from app.modules.system.models import Tenant, User', 'from app.modules.system.models import Tenant, User, UserRole')
            
            with open(dep, 'w', encoding='utf-8') as file:
                file.write(c)

if __name__ == "__main__":
    fix_all()
    print("Done")
