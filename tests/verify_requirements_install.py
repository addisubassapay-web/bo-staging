#!/usr/bin/env python3
"""Create a fresh venv and verify backend requirements install cleanly."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path


APP = Path("/app")
REQ = APP / "backend" / "requirements.txt"
VENV_DIR = Path("/tmp/mercari_backend_requirements_iter35_venv")
LOG = APP / "test_reports" / "requirements_install_iteration35.log"


def run_step(name: str, cmd: list[str]) -> dict:
    start = time.monotonic()
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    elapsed = round(time.monotonic() - start, 2)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"\n===== {name} ({elapsed}s, exit {proc.returncode}) =====\n")
        handle.write(" ".join(cmd) + "\n")
        handle.write(proc.stdout)
        handle.write("\n")
    return {
        "name": name,
        "exit_code": proc.returncode,
        "elapsed_seconds": elapsed,
        "output_tail": proc.stdout[-4000:],
    }


def main() -> int:
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    venv.EnvBuilder(with_pip=True, clear=True).create(VENV_DIR)
    python = VENV_DIR / "bin" / "python"
    steps = [
        run_step("upgrade_pip", [str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]),
        run_step("install_requirements", [str(python), "-m", "pip", "install", "-r", str(REQ)]),
        run_step(
            "import_declared_runtime_packages",
            [
                str(python),
                "-c",
                "import starlette, botocore, aiosmtplib, httpx, arq, redis, apify_client, fastapi, motor, pymongo, pydantic; print('imports ok')",
            ],
        ),
    ]
    result = {
        "ok": all(step["exit_code"] == 0 for step in steps),
        "venv": str(VENV_DIR),
        "requirements": str(REQ),
        "log": str(LOG),
        "steps": steps,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())