from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEAM_NAME = "ArionStrategists"
AGENT_NAME = "ArionAgent"
ANAC_ZIP_NAME = f"{TEAM_NAME}_{AGENT_NAME}.zip"
REQUIRED_IN_ZIP = {
    "arion_strategists/arion_agent.py",
    "arion_strategists/helpers/runner.py",
    "requirements.txt",
    "arion_strategists/__init__.py",
    "arion_strategists/helpers/__init__.py",
}
ALLOWED_HELPERS = {
    "arion_strategists/helpers/__init__.py",
    "arion_strategists/helpers/runner.py",
}
ALLOWED_TOP_LEVEL = {
    "requirements.txt",
    "arion_strategists/arion_agent.py",
    "arion_strategists/__init__.py",
    "arion_strategists/helpers/runner.py",
    "arion_strategists/helpers/__init__.py",
}


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def compile_check() -> None:
    _run([sys.executable, "-m", "py_compile", "arion_strategists/arion_agent.py"], ROOT)
    _run([sys.executable, "-m", "py_compile", "arion_strategists/helpers/runner.py"], ROOT)


def smoke_test() -> None:
    _run([sys.executable, "-m", "arion_strategists.arion_agent", "std"], ROOT)


def benchmark_and_save() -> None:
    _run([sys.executable, "-m", "arion_strategists.helpers.runner", "benchmark-std-save"], ROOT)


def sweep_and_save() -> None:
    _run([sys.executable, "-m", "arion_strategists.helpers.runner", "sweep-std-save"], ROOT)


def create_submission_zip() -> Path:
    zip_path = ROOT / "submission.zip"
    if zip_path.exists():
        zip_path.unlink()

    excluded_prefixes = (".venv/", ".git/", "dist/", "arion_strategists/report/")
    excluded_names = {
        "docker-compose.yml",
        "docker-run.bat",
        "docker-run.sh",
        "Dockerfile",
        "README.md",
        ".gitignore",
        ".envrc",
        ".python-version",
        "pyrightconfig.json",
        ".pre-commit-config.yaml",
        "make_submission.sh",
        "make_submission.bat",
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel not in ALLOWED_TOP_LEVEL:
                continue
            if rel.endswith(".pyc"):
                continue
            if rel.endswith(".zip"):
                continue
            if any(rel.startswith(prefix) for prefix in excluded_prefixes):
                continue
            if rel.startswith("arion_strategists/experiments/"):
                continue
            if "/__pycache__/" in f"/{rel}/":
                continue
            if path.name in excluded_names:
                continue
            zf.write(path, rel)

    return zip_path


def verify_submission_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
    missing = sorted(REQUIRED_IN_ZIP - names)
    if missing:
        raise RuntimeError(
            "submission.zip is missing required entries: " + ", ".join(missing)
        )
    disallowed_helpers = sorted(
        n
        for n in names
        if n.startswith("arion_strategists/helpers/") and n not in ALLOWED_HELPERS
    )
    if disallowed_helpers:
        raise RuntimeError(
            "submission.zip contains non-runtime helper files: "
            + ", ".join(disallowed_helpers)
        )
    print("submission.zip verification passed")


def publish_anac_zip(submission_zip: Path) -> Path:
    """Copy verified submission.zip to the ANAC portal filename."""
    anac_zip = ROOT / ANAC_ZIP_NAME
    if anac_zip.exists():
        anac_zip.unlink()
    anac_zip.write_bytes(submission_zip.read_bytes())
    verify_submission_zip(anac_zip)
    print(f"ANAC upload zip ready: {anac_zip}")
    return anac_zip


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run submission preflight checks for SCML std agent"
    )
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--run-benchmark", action="store_true")
    parser.add_argument("--run-sweep", action="store_true")
    args = parser.parse_args()

    compile_check()
    if not args.skip_smoke:
        smoke_test()
    if args.run_benchmark:
        benchmark_and_save()
    if args.run_sweep:
        sweep_and_save()

    zip_path = create_submission_zip()
    verify_submission_zip(zip_path)
    anac_zip = publish_anac_zip(zip_path)
    print(f"All preflight checks passed: {zip_path}")
    print(f"Upload this file to ANAC: {anac_zip}")


if __name__ == "__main__":
    main()
