#!/usr/bin/env python3
"""Full backend direct-import audit for deployment-readiness verification.

Scans every Python file under /app/backend except files inside a tests directory,
then verifies every non-stdlib, non-local top-level import has a direct entry in
/app/backend/requirements.txt.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


APP = Path("/app")
BACKEND = APP / "backend"
REQUIREMENTS = BACKEND / "requirements.txt"

REQ_IMPORT_MAP = {
    "aiosmtplib": "aiosmtplib",
    "apify-client": "apify_client",
    "arq": "arq",
    "bcrypt": "bcrypt",
    "boto3": "boto3",
    "botocore": "botocore",
    "cryptography": "cryptography",
    "email-validator": "email_validator",
    "emergentintegrations": "emergentintegrations",
    "fastapi": "fastapi",
    "httpx": "httpx",
    "jq": "jq",
    "motor": "motor",
    "numpy": "numpy",
    "pandas": "pandas",
    "passlib": "passlib",
    "pydantic": "pydantic",
    "pyjwt": "jwt",
    "pymongo": "pymongo",
    "python-dotenv": "dotenv",
    "python-jose": "jose",
    "python-multipart": "multipart",
    "redis": "redis",
    "requests": "requests",
    "requests-oauthlib": "requests_oauthlib",
    "starlette": "starlette",
    "typer": "typer",
    "uvicorn": "uvicorn",
}
PACKAGE_BY_IMPORT = {import_name: pkg for pkg, import_name in REQ_IMPORT_MAP.items()}


def parse_requirements() -> dict[str, str]:
    reqs: dict[str, str] = {}
    for raw_line in REQUIREMENTS.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~; ]", line, maxsplit=1)[0].lower().replace("_", "-")
        reqs[name] = line
    return reqs


def local_top_level_imports() -> set[str]:
    local = set()
    for child in BACKEND.iterdir():
        if child.name.startswith(".") or child.name == "tests":
            continue
        if child.is_file() and child.suffix == ".py":
            local.add(child.stem)
        elif child.is_dir():
            local.add(child.name)
    return local


def backend_python_files() -> list[Path]:
    return sorted(
        path
        for path in BACKEND.rglob("*.py")
        if "tests" not in path.relative_to(BACKEND).parts and "__pycache__" not in path.parts
    )


def imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module.split(".", 1)[0])
    return imports


def audit() -> dict:
    reqs = parse_requirements()
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    local = local_top_level_imports()
    third_party: dict[str, list[str]] = {}
    parse_errors = []

    for path in backend_python_files():
        try:
            imports = imports_in(path)
        except SyntaxError as exc:
            parse_errors.append({"file": str(path.relative_to(APP)), "error": str(exc)})
            continue
        for name in imports:
            if name in stdlib or name in local:
                continue
            third_party.setdefault(name, []).append(str(path.relative_to(APP)))

    missing = []
    for import_name, files in sorted(third_party.items()):
        expected_pkg = PACKAGE_BY_IMPORT.get(import_name, import_name.replace("_", "-"))
        if expected_pkg.lower() not in reqs:
            missing.append(
                {
                    "import": import_name,
                    "expected_requirement": expected_pkg,
                    "files": sorted(files),
                }
            )

    specifically_required = [
        "aiosmtplib",
        "httpx",
        "arq",
        "redis",
        "apify-client",
        "starlette",
        "botocore",
    ]
    return {
        "ok": not missing and not parse_errors,
        "backend_file_count_excluding_tests": len(backend_python_files()),
        "local_import_roots": sorted(local),
        "third_party_imports": {k: sorted(v) for k, v in sorted(third_party.items())},
        "requirements_count": len(reqs),
        "specifically_required_present": {pkg: (pkg in reqs) for pkg in specifically_required},
        "missing_requirements": missing,
        "parse_errors": parse_errors,
    }


def main() -> int:
    result = audit()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())