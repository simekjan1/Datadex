from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path


KOREN = Path(__file__).resolve().parent
VENV = KOREN / ".venv"
LOCK = KOREN / "requirements.lock"
INTERNI = KOREN / "interni"


def interpreter() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def zavislosti() -> list[str]:
    if not LOCK.is_file():
        raise FileNotFoundError("Chybí requirements.lock.")
    return [radek.strip() for radek in LOCK.read_text(encoding="utf-8").splitlines() if radek.strip() and not radek.lstrip().startswith("#")]


def prostredi() -> dict[str, str]:
    env = os.environ.copy()
    docasne = INTERNI / "docasne"
    docasne.mkdir(parents=True, exist_ok=True)
    env.update({
        "TEMP": str(docasne),
        "TMP": str(docasne),
        "PIP_CACHE_DIR": str(INTERNI / "pip-cache"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(INTERNI / "pycache"),
    })
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Bezpečná instalace lokální znalostní databáze do .venv")
    parser.add_argument("--check", action="store_true", help="jen zkontroluje předpoklady a nic nevytváří")
    parser.add_argument("--repair", action="store_true", help="znovu vytvoří součásti existujícího virtuálního prostředí")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        print("Je vyžadován Python 3.10 nebo novější.")
        return 1
    deps = zavislosti()
    print(f"Python {sys.version.split()[0]} je podporovaný. Externí závislosti: {len(deps)}.")
    if args.check:
        print("Kontrola instalačních předpokladů proběhla úspěšně.")
        return 0
    if VENV.exists() and not VENV.is_dir():
        print("Cesta .venv existuje, ale není složkou; nebyla změněna.")
        return 1
    try:
        venv.EnvBuilder(with_pip=True, upgrade=args.repair and VENV.exists()).create(VENV)
        py = interpreter()
        if not py.is_file():
            raise OSError(f"Ve virtuálním prostředí chybí interpreter: {py}")
        if deps:
            subprocess.run([str(py), "-m", "pip", "install", "--requirement", str(LOCK)], cwd=KOREN, env=prostredi(), check=True)
        subprocess.run([str(py), "-B", str(KOREN / "skript" / "cms.py"), "--help"], cwd=KOREN, env=prostredi(), check=True, stdout=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as chyba:
        print(f"Instalace se nezdařila: {chyba}")
        print("Dosavadní data a konfigurace nebyly měněny. Spusťte instalovat.py --repair nebo zkontrolujte oprávnění.")
        return 1
    print("Instalace je připravena. Spusťte Spustit.bat, nebo .venv/bin/python skript/cms.py na Linuxu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
