#!/usr/bin/env python3
"""Focused deployment-readiness verification for the reported deploy blocker."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


APP = Path("/app")
BACKEND = APP / "backend"
PREVIEW_BASE = "https://seller-health-portal.preview.emergentagent.com"

STDLIB = set(sys.stdlib_module_names) | {"__future__"}
LOCAL_TOP_LEVEL = {
    "apify_sync",
    "image_pools",
    "routers",
    "server",
    "services",
    "shipping_providers",
}
REQ_IMPORT_MAP = {
    "apify-client": "apify_client",
    "bcrypt": "bcrypt",
    "boto3": "boto3",
    "cryptography": "cryptography",
    "email-validator": "email_validator",
    "emergentintegrations": "emergentintegrations",
    "fastapi": "fastapi",
    "httpx": "httpx",
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
    "requests": "requests",
    "requests-oauthlib": "requests_oauthlib",
    "uvicorn": "uvicorn",
    "aiosmtplib": "aiosmtplib",
    "arq": "arq",
    "redis": "redis",
}
PACKAGE_BY_IMPORT = {v: k for k, v in REQ_IMPORT_MAP.items()}


def parse_requirements() -> dict[str, str]:
    reqs: dict[str, str] = {}
    for line in (BACKEND / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~ ]", line, maxsplit=1)[0].lower()
        reqs[name] = line
    return reqs


def runtime_py_files() -> list[Path]:
    files = []
    files.extend(BACKEND.glob("*.py"))
    files.extend((BACKEND / "routers").glob("*.py"))
    files.extend((BACKEND / "services").glob("*.py"))
    return sorted(files)


def imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                found.add(node.module.split(".", 1)[0])
    return found


def check_requirements() -> dict:
    reqs = parse_requirements()
    all_imports: dict[str, list[str]] = {}
    for path in runtime_py_files():
        for name in imports_in(path):
            if name in STDLIB or name in LOCAL_TOP_LEVEL:
                continue
            all_imports.setdefault(name, []).append(str(path.relative_to(APP)))
    missing = []
    for name, paths in sorted(all_imports.items()):
        pkg = PACKAGE_BY_IMPORT.get(name, name.replace("_", "-"))
        if pkg.lower() not in reqs:
            missing.append({"import": name, "expected_requirement": pkg, "files": paths})
    required_recent = ["aiosmtplib", "httpx", "arq", "redis", "apify-client"]
    recent_present = {pkg: (pkg in reqs) for pkg in required_recent}
    return {
        "ok": not missing and all(recent_present.values()),
        "runtime_file_count": len(runtime_py_files()),
        "third_party_imports": sorted(all_imports),
        "requirements_count": len(reqs),
        "recent_packages_present": recent_present,
        "missing_requirements": missing,
    }


def check_endpoints() -> dict:
    cases = [
        ("root", "/api/", "json"),
        ("sitemap", "/api/sitemap_index.xml", "xml"),
        ("robots", "/api/robots.txt", "text"),
        ("wallet_ticker", "/api/wallet/ticker", "json"),
        ("indexnow_key", "/api/indexnow-key.txt", "text"),
    ]
    results = []
    with requests.Session() as session:
        for name, path, expected_kind in cases:
            url = urljoin(PREVIEW_BASE, path)
            try:
                response = session.get(url, timeout=20)
                content_type = response.headers.get("content-type", "")
                body = response.text[:300]
                result = {
                    "name": name,
                    "path": path,
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "body_preview": body,
                }
                if expected_kind == "json":
                    result["json"] = response.json()
                    result["kind_ok"] = isinstance(result["json"], (dict, list))
                elif expected_kind == "xml":
                    result["kind_ok"] = "xml" in content_type.lower() or body.lstrip().startswith("<?xml") or "<sitemapindex" in body
                else:
                    result["kind_ok"] = bool(response.text.strip())
                results.append(result)
            except Exception as exc:  # noqa: BLE001 - test artifact should capture any failure
                results.append({"name": name, "path": path, "error": repr(exc), "status_code": None, "kind_ok": False})
    root_ok = any(
        r.get("name") == "root"
        and r.get("status_code") == 200
        and r.get("json") == {"message": "Mercari Clone API", "status": "ok"}
        for r in results
    )
    endpoints_ok = all(r.get("status_code") == 200 and r.get("kind_ok") for r in results)
    return {"ok": root_ok and endpoints_ok, "root_ok": root_ok, "endpoints_ok": endpoints_ok, "results": results}


def main() -> int:
    output = {
        "requirements_check": check_requirements(),
        "endpoint_check": check_endpoints(),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["requirements_check"]["ok"] and output["endpoint_check"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())