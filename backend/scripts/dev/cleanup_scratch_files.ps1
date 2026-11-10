<#
    cleanup_scratch_files.ps1

    Removes confirmed-dead debug/scratch files and confirmed-dead code
    packages from the backend/ tree. Run this from the backend/ folder:

        cd C:\Users\DELL\Downloads\ERP-main\backend
        powershell -File cleanup_scratch_files.ps1

    Everything in here was verified (grep across the whole app/ tree plus
    manual read of the candidate files) to have zero live references before
    being added to this list. Nothing under app/plugins/hospitality,
    app/plugins/recruitment, app/plugins/rental, app/plugins/travel, or
    app/plugins/whatsapp is touched - those are still live and mounted.

    upgrade_tenants.py and verify_e2e.py are NOT deleted - they were moved
    to backend/scripts/ (already written there); this script only deletes
    the stale copies left at the backend/ root.
#>

$ErrorActionPreference = 'SilentlyContinue'
$root = $PSScriptRoot
if (-not $root) { $root = Get-Location }

function Remove-IfExists {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [switch]$Recurse
    )
    $full = Join-Path $root $RelativePath
    if (Test-Path -LiteralPath $full) {
        if ($Recurse) {
            Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            Remove-Item -LiteralPath $full -Force -ErrorAction SilentlyContinue
        }
        if (-not (Test-Path -LiteralPath $full)) {
            Write-Host "[deleted] $RelativePath"
        } else {
            Write-Host "[FAILED to delete] $RelativePath"
        }
    } else {
        Write-Host "[skip, not found] $RelativePath"
    }
}

Write-Host "=== Deleting scratch/debug files under backend/ ==="

$scratchFiles = @(
    'check_progress.py',
    'check_tables.py',
    'check_tenants.py',
    'check_users.py',
    'clear_users.py',
    'create_cheques_table.py',
    'delete_users.py',
    'filter_migration.py',
    'fix_all.py',
    'fix_deps.py',
    'fix_roles.py',
    'get_tenant.py',
    'reset_db.py',
    'routes.txt',
    'run_outbox_test.py',
    'test_err.txt',
    'test_mixin.py',
    'test_reg.py',
    'test_req.json',
    'test_sqlmodel.py',
    'pytest.ini.bak',
    'alembic_upgrade_out.txt'
)
foreach ($f in $scratchFiles) {
    Remove-IfExists -RelativePath $f
}

Write-Host ""
Write-Host "=== Deleting scratch/ and tests/modules.bak/ folders ==="
Remove-IfExists -RelativePath 'scratch' -Recurse
Remove-IfExists -RelativePath 'tests\modules.bak' -Recurse

Write-Host ""
Write-Host "=== Removing upgrade_tenants.py / verify_e2e.py from backend/ root ==="
Write-Host "    (already moved to backend/scripts/ - see that folder)"
Remove-IfExists -RelativePath 'upgrade_tenants.py'
Remove-IfExists -RelativePath 'verify_e2e.py'

Write-Host ""
Write-Host "=== Deleting dead code packages under backend/app/ ==="
Write-Host "    (app/alembic/tenant/env.py's 'import app.plugins.inventory.models'"
Write-Host "     line was already removed before this script was written - verify"
Write-Host "     that edit landed before running this, or tenant migrations will break.)"

Remove-IfExists -RelativePath 'app\plugins\sales' -Recurse
Remove-IfExists -RelativePath 'app\plugins\purchases' -Recurse
Remove-IfExists -RelativePath 'app\plugins\inventory' -Recurse
Remove-IfExists -RelativePath 'app\plugins\_deprecated_shipping_stub' -Recurse
Remove-IfExists -RelativePath 'app\core\dashboard' -Recurse

Write-Host ""
Write-Host "=== Deleting dead contacts service.py (broken model references, not imported anywhere) ==="
Remove-IfExists -RelativePath 'app\modules\contacts\service.py'

Write-Host ""
Write-Host "=== Cleanup complete ==="
