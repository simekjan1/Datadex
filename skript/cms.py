from __future__ import annotations

import argparse
import sys
from pathlib import Path

KOREN = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from moduly.konfigurace import inicializuj
from moduly.kontrola import zkontroluj
from moduly.menu import hlavni_menu, zobraz_souhrn
from moduly.prevod import generuj


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline znalostní databáze")
    parser.add_argument("--init", action="store_true", help="vytvoří výchozí strukturu bez interaktivního průvodce")
    parser.add_argument("--build", action="store_true", help="inkrementálně vygeneruje web")
    parser.add_argument("--full", action="store_true", help="úplně vygeneruje web")
    parser.add_argument("--check", action="store_true", help="zkontroluje zdroje, odkazy a konfiguraci")
    args = parser.parse_args()
    try:
        if args.init:
            vytvorene = inicializuj()
            print(f"Inicializace dokončena. Nově vytvořené položky: {len(vytvorene)}")
            return 0
        if args.build or args.full:
            zobraz_souhrn(generuj(uplne=args.full))
            return 0
        if args.check:
            inicializuj()
            zpravy, log = zkontroluj()
            for z in zpravy: print(z)
            print(f"Protokol: {log}")
            return 1 if any(z.startswith(("Chyba", "Konflikt", "Neplatný", "Nepovolený")) for z in zpravy) else 0
        hlavni_menu()
        return 0
    except KeyboardInterrupt:
        print("\nOperace byla přerušena uživatelem.")
        return 130
    except (OSError, ValueError, MemoryError) as chyba:
        print(f"Program nemůže pokračovat: {chyba}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
