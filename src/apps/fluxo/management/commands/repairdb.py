"""
Comando Django: python manage.py repairdb [--database default] [--dry-run]

Verifica e, se necessário, repara o arquivo SQLite associado ao alias de
banco informado (usa settings.DATABASES), seguindo o mesmo fluxo seguro
de scripts/repair_sqlite.py (backup -> integrity_check -> reindex/vacuum
-> rebuild via dump -> troca atômica só se validado).

Instalação:
    Copie esta pasta 'management/commands/repairdb.py' para dentro de um
    app do seu projeto Django, por exemplo:
        yourapp/management/commands/repairdb.py
    e coloque scripts/sqlite_repair_core.py em algum lugar importável
    (ex.: yourapp/management/commands/sqlite_repair_core.py, ou instale
    scripts/ no PYTHONPATH).
"""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

try:
    from .sqlite_repair_core import repair_database
except ImportError:  # fallback se sqlite_repair_core estiver em scripts/ no PYTHONPATH
    from sqlite_repair_core import repair_database


class Command(BaseCommand):
    help = "Verifica a integridade do banco SQLite e repara automaticamente se necessário."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Alias do banco em settings.DATABASES (padrão: 'default')",
        )
        parser.add_argument(
            "--backup-dir",
            default=None,
            help="Diretório para salvar o backup (padrão: mesma pasta do banco)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Só faz backup + integrity_check, não altera nada",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Autoriza a substituição mesmo com perda de dados detectada "
                "(menos linhas que o backup). Revise o relatório antes de usar."
            ),
        )

    def handle(self, *args, **options):
        alias = options["database"]
        db_config = settings.DATABASES.get(alias)

        if not db_config:
            raise CommandError(f"Alias de banco '{alias}' não encontrado em settings.DATABASES")

        if "sqlite3" not in db_config["ENGINE"]:
            raise CommandError(
                f"repairdb só funciona com SQLite. O alias '{alias}' usa {db_config['ENGINE']}"
            )

        db_path = db_config["NAME"]
        self.stdout.write(f"Verificando banco: {db_path}")

        report = repair_database(
            str(db_path),
            backup_dir=options["backup_dir"],
            dry_run=options["dry_run"],
            force=options["force"],
        )

        self.stdout.write("")
        self.stdout.write(report.summary())
        self.stdout.write("")

        if report.original_ok:
            self.stdout.write(self.style.SUCCESS("Banco íntegro, nada foi alterado."))
            return

        if report.final_ok:
            self.stdout.write(
                self.style.WARNING(
                    f"Banco reparado com sucesso (estratégia: {report.strategy_used}). "
                    f"Backup original preservado em: {report.backup_path}"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "Não foi possível reparar automaticamente. "
                    "O banco original NÃO foi alterado. "
                    f"Backup disponível em: {report.backup_path}"
                )
            )
            sys.exit(1)
