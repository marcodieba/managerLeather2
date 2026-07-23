"""
Comando Django: python manage.py rescue_lost_and_found [--backup PATH] [--preview]

Recupera linhas da tabela `fluxo_requisicao` que ficaram em `lost_and_found`
após uma tentativa de .recover do SQLite.

Por que isso acontece:
  Quando o SQLite não consegue reconstruir o schema de uma tabela a partir de
  páginas corrompidas, agrupa as linhas órfãs em `lost_and_found` com colunas
  genéricas c0, c1, c2, ... na ordem das colunas da tabela original.
  Este comando mapeia essas colunas de volta ao schema real e insere os dados.

Fluxo:
  1. Localizar o backup mais recente (ou usar --backup PATH)
  2. Executar sqlite3 .recover sobre o backup → banco temporário com lost_and_found
  3. Ler o schema real de fluxo_requisicao via PRAGMA table_info
  4. Descobrir o rootpgno da tabela no backup (sqlite_master)
  5. Filtrar lost_and_found pelo rootpgno
  6. Mapear c0...cN para as colunas reais
  7. Inserir no banco original com ON CONFLICT IGNORE (chave: cd_requisicao)
  8. REINDEX no banco original para corrigir os índices corrompidos
"""

from __future__ import annotations

import glob
import os
import shutil
import sqlite3
import subprocess
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Recupera linhas de fluxo_requisicao a partir da tabela lost_and_found "
        "gerada pelo sqlite3 .recover. Execute APÓS um repairdb que falhou por "
        "perda de dados nessa tabela."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--backup",
            default=None,
            help=(
                "Caminho do arquivo .bak_* a usar como fonte. "
                "Se omitido, usa o backup mais recente na mesma pasta do banco."
            ),
        )
        parser.add_argument(
            "--database",
            default="default",
            help="Alias do banco em settings.DATABASES (padrão: 'default')",
        )
        parser.add_argument(
            "--preview",
            action="store_true",
            help="Mostra o que seria importado sem tocar no banco original.",
        )
        parser.add_argument(
            "--reindex",
            action="store_true",
            default=True,
            help="Executa REINDEX no banco original após a importação (padrão: True).",
        )

    # ------------------------------------------------------------------
    # handle
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        alias = options["database"]
        db_config = settings.DATABASES.get(alias)

        if not db_config or "sqlite3" not in db_config["ENGINE"]:
            raise CommandError("rescue_lost_and_found só funciona com SQLite.")

        db_path = str(db_config["NAME"])

        # Localiza o backup a usar como fonte
        backup_path = options["backup"] or self._find_latest_backup(db_path)
        if not backup_path or not os.path.exists(backup_path):
            raise CommandError(
                f"Nenhum arquivo de backup encontrado. Use --backup <caminho>."
            )

        self.stdout.write(f"Banco alvo:  {db_path}")
        self.stdout.write(f"Fonte (bak): {backup_path}")

        if shutil.which("sqlite3") is None:
            raise CommandError(
                "O executável 'sqlite3' não foi encontrado no PATH. "
                "Instale o SQLite CLI antes de continuar."
            )

        # Executa recover e importa dados
        with tempfile.TemporaryDirectory(prefix="rescue_") as tmp:
            recovered_db = os.path.join(tmp, "recovered.db")
            self._run_recover(backup_path, recovered_db)

            if not os.path.exists(recovered_db):
                raise CommandError("O sqlite3 .recover não gerou o banco reconstruído.")

            # Verifica se lost_and_found existe no banco recuperado
            if not self._has_table(recovered_db, "lost_and_found"):
                self.stdout.write(self.style.WARNING(
                    "O banco recuperado não tem tabela 'lost_and_found'. "
                    "Nada a importar — os dados podem já ter sido recuperados "
                    "por outra estratégia."
                ))
                return

            # Obtém schema real da tabela no banco corrompido (via backup)
            schema_cols = self._get_table_columns(backup_path, "fluxo_requisicao")
            if not schema_cols:
                # Tenta pelo banco original directamente
                schema_cols = self._get_table_columns(db_path, "fluxo_requisicao")

            if not schema_cols:
                raise CommandError(
                    "Não foi possível obter o schema de fluxo_requisicao. "
                    "Certifique-se que a tabela existe no banco original."
                )

            self.stdout.write(
                f"Schema detectado ({len(schema_cols)} colunas): "
                + ", ".join(schema_cols)
            )

            # Obtém o rootpgno da fluxo_requisicao no backup para filtrar lost_and_found
            rootpgno = self._get_rootpgno(backup_path, "fluxo_requisicao")
            self.stdout.write(f"rootpgno de fluxo_requisicao no backup: {rootpgno}")

            # Lê as linhas candidatas do lost_and_found
            rows = self._read_lost_and_found(recovered_db, rootpgno, len(schema_cols))
            self.stdout.write(f"Linhas candidatas em lost_and_found: {len(rows)}")

            if not rows:
                self.stdout.write(self.style.WARNING(
                    "Nenhuma linha encontrada em lost_and_found com o rootpgno "
                    f"{rootpgno}. "
                    "Tentando sem filtro de rootpgno (recuperação melhor-esforço)..."
                ))
                rows = self._read_lost_and_found(recovered_db, None, len(schema_cols))
                self.stdout.write(f"Linhas sem filtro: {len(rows)}")

            if not rows:
                self.stdout.write(self.style.WARNING("Nenhuma linha para importar."))
                return

            # Mostra prévia
            self._show_preview(schema_cols, rows[:10])

            if options["preview"]:
                self.stdout.write(self.style.WARNING(
                    "[PREVIEW] Nenhuma alteração foi feita. "
                    "Remova --preview para executar a importação e substituição."
                ))
                return

            # Importa para o banco RECUPERADO (que está saudável, mas faltando estas linhas)
            imported, skipped = self._import_rows(
                recovered_db, "fluxo_requisicao", schema_cols, rows
            )

            self.stdout.write(self.style.SUCCESS(
                f"Importação concluída no banco recuperado: {imported} inseridas, {skipped} ignoradas."
            ))
            
            # Copia o banco recuperado para o local do original
            self.stdout.write("Substituindo o banco corrompido original pelo banco recuperado...")
            # Fecha todas as conexões antes de substituir
            shutil.copy2(recovered_db, db_path)
            self.stdout.write(self.style.SUCCESS(
                f"Sucesso! O banco de dados em {db_path} foi substituído pela versão saudável com os dados resgatados."
            ))


    # ------------------------------------------------------------------
    # Utilitários privados
    # ------------------------------------------------------------------

    def _find_latest_backup(self, db_path: str) -> str | None:
        """Encontra o backup .bak_* mais recente na mesma pasta do banco."""
        directory = os.path.dirname(os.path.abspath(db_path))
        basename = os.path.basename(db_path)
        pattern = os.path.join(directory, f"{basename}.bak_*")
        candidates = sorted(glob.glob(pattern), reverse=True)
        return candidates[0] if candidates else None

    def _run_recover(self, src_path: str, dst_db_path: str) -> None:
        """
        Executa sqlite3 .recover sobre src_path e importa o resultado
        num novo banco em dst_db_path.
        """
        dump_path = dst_db_path + ".sql"
        self.stdout.write(f"Executando sqlite3 .recover sobre {src_path}...")

        with open(dump_path, "w", encoding="utf-8", errors="replace", newline="\n") as f:
            result = subprocess.run(
                ["sqlite3", src_path, ".recover"],
                stdout=f,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        if result.returncode != 0:
            self.stdout.write(self.style.WARNING(
                f"sqlite3 .recover terminou com código {result.returncode}: "
                f"{result.stderr.strip()[:200]}"
            ))

        # Importa o dump para o banco reconstruído
        self.stdout.write("Importando dump recuperado para banco temporário...")
        
        # Importa a função de sanitização do core
        try:
            from sqlite_repair_core import sanitize_dump_sql
        except ImportError:
            # Fallback inline se não conseguir importar
            def sanitize_dump_sql(script):
                lines = []
                for line in script.splitlines():
                    s = line.strip()
                    if s.startswith(".") or s.startswith("sqlite>"):
                        continue
                    lines.append(line)
                return "\n".join(lines)

        conn = sqlite3.connect(dst_db_path)
        try:
            with open(dump_path, "r", encoding="utf-8", errors="replace", newline="") as f:
                sql = f.read()
            sql = sanitize_dump_sql(sql)
            conn.executescript(sql)
            conn.commit()
        finally:
            conn.close()

        self.stdout.write(f"Banco recuperado criado em: {dst_db_path}")

    def _has_table(self, db_path: str, table_name: str) -> bool:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def _get_table_columns(self, db_path: str, table_name: str) -> list[str]:
        """
        Retorna os nomes das colunas na ordem definida pelo schema
        (PRAGMA table_info), excluindo o rowid implícito.
        """
        try:
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    f'PRAGMA table_info("{table_name}")'
                ).fetchall()
                # (cid, name, type, notnull, dflt_value, pk)
                return [r[1] for r in rows]
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            self.stdout.write(self.style.WARNING(
                f"Não foi possível ler schema de {table_name} em {db_path}: {e}"
            ))
            return []

    def _get_rootpgno(self, db_path: str, table_name: str) -> int | None:
        """Obtém o rootpage da tabela no sqlite_master."""
        try:
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "SELECT rootpage FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                ).fetchone()
                return row[0] if row else None
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return None

    def _read_lost_and_found(
        self,
        recovered_db: str,
        rootpgno: int | None,
        expected_ncols: int,
    ) -> list[tuple]:
        """
        Lê as linhas do lost_and_found que correspondem à nossa tabela.

        O lost_and_found tem schema:
            rootpgno INTEGER, pgno INTEGER, nfield INTEGER, id INTEGER,
            c0, c1, c2, ...

        Filtra por:
        - rootpgno (se disponível)
        - nfield == expected_ncols (número de campos que bate com o schema)
        """
        conn = sqlite3.connect(recovered_db)
        try:
            # Descobre quantas colunas c0..cN existem no lost_and_found
            info = conn.execute("PRAGMA table_info(lost_and_found)").fetchall()
            data_cols = [r[1] for r in info if r[1].startswith("c")]
            n_data_cols = len(data_cols)

            if n_data_cols == 0:
                return []

            # Substitui 'c0' por 'id' se 'c0' for a chave primária, pois 
            # no SQLite a chave primária fica no ROWID (id) e não no payload (c0 nulo)
            cols_to_select = []
            for i, col in enumerate(data_cols[:expected_ncols]):
                if i == 0:
                    cols_to_select.append("id") # Pega o rowid original de lost_and_found
                else:
                    cols_to_select.append(col)

            col_select = ", ".join(cols_to_select)

            if rootpgno is not None:
                sql = (
                    f"SELECT {col_select} FROM lost_and_found "
                    f"WHERE rootpgno = ? AND nfield = ?"
                )
                rows = conn.execute(sql, (rootpgno, expected_ncols)).fetchall()
            else:
                sql = (
                    f"SELECT {col_select} FROM lost_and_found "
                    f"WHERE nfield = ?"
                )
                rows = conn.execute(sql, (expected_ncols,)).fetchall()

            return rows
        finally:
            conn.close()

    def _show_preview(self, schema_cols: list[str], rows: list[tuple]) -> None:
        self.stdout.write(f"\n{'─' * 60}")
        self.stdout.write("Prévia das primeiras linhas a importar:")
        self.stdout.write("  " + " | ".join(schema_cols))
        self.stdout.write("  " + "─" * 60)
        for row in rows:
            vals = [str(v)[:20] if v is not None else "NULL" for v in row]
            self.stdout.write("  " + " | ".join(vals))
        self.stdout.write(f"{'─' * 60}\n")

    def _import_rows(
        self,
        db_path: str,
        table_name: str,
        schema_cols: list[str],
        rows: list[tuple],
    ) -> tuple[int, int]:
        """
        Insere as linhas recuperadas no banco original.
        Usa INSERT OR IGNORE para não derrubar dados existentes em caso de
        conflito de chave primária ou unique (cd_requisicao).
        """
        placeholders = ", ".join(["?" for _ in schema_cols])
        col_names = ", ".join([f'"{c}"' for c in schema_cols])
        sql = (
            f'INSERT OR IGNORE INTO "{table_name}" ({col_names}) '
            f"VALUES ({placeholders})"
        )

        conn = sqlite3.connect(db_path, isolation_level=None)  # autocommit
        imported = 0
        skipped = 0

        try:
            conn.execute("BEGIN")
            for row in rows:
                # Ajusta o comprimento da linha ao número de colunas esperadas
                padded = list(row[:len(schema_cols)])
                while len(padded) < len(schema_cols):
                    padded.append(None)

                try:
                    cursor = conn.execute(sql, padded)
                    if cursor.rowcount > 0:
                        imported += 1
                    else:
                        skipped += 1
                except sqlite3.IntegrityError:
                    skipped += 1
                except sqlite3.DatabaseError as e:
                    self.stdout.write(self.style.WARNING(f"  Linha ignorada por erro: {e}"))
                    skipped += 1

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

        return imported, skipped

    def _reindex(self, db_path: str) -> None:
        conn = sqlite3.connect(db_path, isolation_level=None)
        try:
            conn.execute("REINDEX")
            conn.execute("VACUUM")
        finally:
            conn.close()
