#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# High entropy strings, JWT secrets, passwords, or specific keys like PEPPER and ETA credentials
SECRET_PATTERNS = [
    r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]+['\"]",
    r"(?i)(secret|token|api_key|apikey|access_key)\s*=\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
    r"(?i)PEPPER\s*=\s*['\"][^'\"]+['\"]",
    r"(?i)ETA_CLIENT_SECRET\s*=\s*['\"][^'\"]+['\"]",
    r"(?i)BOSTA_WEBHOOK_KEY\s*=\s*['\"][^'\"]+['\"]",
    r"(?i)MYLERZ_WEBHOOK_KEY\s*=\s*['\"][^'\"]+['\"]",
    r"(?i)JWT_SECRET\s*=\s*['\"][^'\"]+['\"]",
]

COMPILED_PATTERNS = [re.compile(p) for p in SECRET_PATTERNS]

IGNORE_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".pytest_cache",
}

IGNORE_FILES = {
    "conftest.py",      # Allowed to have mock secrets for testing
    "audit_secrets.py", # This file itself
}

def scan_file(filepath: Path) -> list[tuple[int, str, str]]:
    """Scan a single file for secrets and return a list of violations."""
    violations = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                for pattern in COMPILED_PATTERNS:
                    if pattern.search(line):
                        # Redact the match slightly to prevent logging the secret itself
                        clean_line = line.strip()
                        if len(clean_line) > 100:
                            clean_line = clean_line[:100] + "..."
                        violations.append((line_no, pattern.pattern, clean_line))
                        break # One violation per line is enough
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return violations


def audit_directory(base_dir: Path, extensions: set[str] | None = None) -> int:
    """Recursively scans a directory for files and checks for secrets."""
    total_violations = 0
    print(f"\nScanning directory: {base_dir}")
    if not base_dir.exists():
        print(f"Skipping {base_dir} (does not exist)")
        return 0

    for root, dirs, files in os.walk(base_dir):
        # Mutate dirs in-place to avoid traversing ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            if file in IGNORE_FILES:
                continue

            filepath = Path(root) / file
            
            # If extensions are specified, only scan those. Otherwise, scan all files.
            if extensions is not None and filepath.suffix not in extensions:
                continue

            violations = scan_file(filepath)
            if violations:
                print(f"❌ LEAK DETECTED in {filepath}:")
                for line_no, pat, content in violations:
                    print(f"   Line {line_no}: [Pattern: {pat}] -> {content}")
                total_violations += len(violations)
                
    return total_violations


def main():
    backend_dir = Path(__file__).parent.parent
    frontend_dir = backend_dir.parent / "frontend"
    
    total_leaks = 0
    
    # 1. Scan backend Python files
    total_leaks += audit_directory(backend_dir / "app", extensions={".py"})
    total_leaks += audit_directory(backend_dir / "scripts", extensions={".py", ".sh"})
    total_leaks += audit_directory(backend_dir / "tests", extensions={".py"})
    
    # 2. Scan Log files
    total_leaks += audit_directory(backend_dir, extensions={".log"})
    
    # 3. Scan Frontend Client Bundles (.next directory)
    # The client bundles can sometimes leak hardcoded environment variables
    next_dir = frontend_dir / ".next"
    if next_dir.exists():
        total_leaks += audit_directory(next_dir, extensions={".js", ".map", ".json"})
    else:
        # Fallback to src directory if no build exists
        total_leaks += audit_directory(frontend_dir / "src", extensions={".ts", ".tsx", ".js", ".jsx"})

    if total_leaks > 0:
        print(f"\n🚨 AUDIT FAILED: {total_leaks} potential secret leaks detected.")
        sys.exit(1)
    else:
        print("\n✅ AUDIT PASSED: No secrets found in scanned files.")
        sys.exit(0)


if __name__ == "__main__":
    main()
