#!/usr/bin/env python3
"""
repair_sqlite.py

Uso:
    python repair_sqlite.py /caminho/para/db.sqlite3
    python repair_sqlite.py /caminho/para/db.sqlite3 --backup-dir /caminho/backups
    python repair_sqlite.py /caminho/para/db.sqlite3 --dry-run
    python repair_sqlite.py /caminho/para/db.sqlite3 --quiet   # só o resumo final

Sai com código 0 se o banco está (ou ficou) íntegro, 1 caso contrário.
"""

import argparse
import logging
import sys

from sqlite_repair_core import repair_database


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica e repara um banco SQLite corrompido.")
    parser.add_argument("db_path", help="Caminho para o arquivo .sqlite3")
    parser.add_argument(
        "--backup-dir",
        default=None,
        help="Diretório onde salvar o backup (padrão: mesma pasta do banco)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Faz backup e integrity_check, mas não altera nada",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suprime logs intermediários, mostra só o resumo final",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Autoriza a substituição do banco original mesmo que o reparo "
            "detecte perda de dados (menos linhas que o backup). Use só "
            "depois de revisar o relatório de perda de dados."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    report = repair_database(
        args.db_path,
        backup_dir=args.backup_dir,
        dry_run=args.dry_run,
        force=args.force,
    )

    print("\n" + "=" * 60)
    print(report.summary())
    print("=" * 60)

    if report.error and not report.final_ok:
        return 1
    if report.final_ok is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
