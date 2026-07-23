"""
sqlite_repair_core.py

Recuperação segura e conservadora de bancos SQLite corrompidos.

Objetivos:
- nunca modificar o banco original durante as tentativas;
- sempre criar backup antes de qualquer ação;
- validar estrutura com quick_check + integrity_check;
- tentar reparo leve (REINDEX + VACUUM) em cópia de trabalho;
- tentar reconstrução por múltiplas estratégias:
    1) sqlite3 .dump
    2) sqlite3 .recover
    3) Python iterdump()
- comparar dados legíveis antes/depois;
- só substituir o original se o candidato estiver íntegro e não perder
  dados legíveis, salvo force=True.

Observações importantes:
- comandos iniciados por ponto (ex.: .dump, .recover, .read) são meta-
  comandos do shell sqlite3, não SQL puro; por isso a saída pode exigir
  saneamento antes de executar via sqlite3.Connection.executescript().
- em Windows, todo I/O textual é tratado explicitamente com UTF-8 e
  fallback controlado para evitar UnicodeDecodeError por cp1252 padrão.
"""

from __future__ import annotations

import csv
import datetime
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger("sqlite_repair")


class RepairError(Exception):
    """Erro fatal durante o processo de reparo."""


@dataclass
class CandidateResult:
    label: str
    db_path: str
    counts: dict[str, int | None]
    imported_dump_encoding: str | None = None
    loss_detected: bool | None = None
    loss_details: list[str] = field(default_factory=list)
    total_rows: int = 0
    lost_rows: int = 0


@dataclass
class RepairReport:
    db_path: str
    backup_path: str | None = None
    original_ok: bool | None = None
    original_quick_ok: bool | None = None
    original_issues: list[str] = field(default_factory=list)
    original_quick_issues: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    strategy_used: str | None = None
    final_ok: bool | None = None
    replaced: bool = False
    forced: bool = False
    error: str | None = None

    baseline_counts: dict[str, int | None] | None = None
    candidate_counts: dict[str, int | None] | None = None
    data_loss_detected: bool | None = None
    data_loss_details: list[str] = field(default_factory=list)
    imported_dump_encoding: str | None = None

    def log(self, msg: str):
        logger.info(msg)
        self.steps.append(msg)

    def summary(self) -> str:
        lines = [
            f"Banco: {self.db_path}",
            f"Backup criado em: {self.backup_path}",
            f"Quick check original OK: {self.original_quick_ok}",
            f"Integridade original OK: {self.original_ok}",
        ]

        if self.original_quick_issues:
            lines.append(f"Quick check original: {self.original_quick_issues[:5]}")

        if self.original_issues and not self.original_ok:
            lines.append(f"Problemas encontrados: {self.original_issues[:5]}")

        if self.strategy_used:
            lines.append(f"Estratégia de reparo usada: {self.strategy_used}")

        if self.imported_dump_encoding:
            lines.append(f"Encoding usado na importação do dump: {self.imported_dump_encoding}")

        if self.baseline_counts is not None:
            lines.append(f"Linhas legíveis no backup (antes): {self.baseline_counts}")

        if self.candidate_counts is not None:
            lines.append(f"Linhas no candidato a substituto (depois): {self.candidate_counts}")

        if self.data_loss_detected is not None:
            lines.append(f"Perda de dados detectada: {self.data_loss_detected}")

        if self.data_loss_details:
            lines.append("Detalhes da perda de dados:")
            for d in self.data_loss_details:
                lines.append(f"  ! {d}")

        lines.append(f"Banco final íntegro: {self.final_ok}")
        lines.append(f"Arquivo original substituído: {self.replaced}" + (" (FORÇADO)" if self.forced else ""))

        if self.error:
            lines.append(f"ERRO: {self.error}")

        lines.append("")
        lines.append("Passos executados:")
        for s in self.steps:
            lines.append(f"  - {s}")

        return "\n".join(lines)


# --------------------------------------------------------------------------
# Utilidades básicas
# --------------------------------------------------------------------------


def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _sqlite_cli_available() -> bool:
    return shutil.which("sqlite3") is not None


def _connect(path: str, *, readonly: bool = False, autocommit: bool = False) -> sqlite3.Connection:
    if readonly:
        uri = f"file:{Path(path).as_posix()}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=30)
    isolation_level = None if autocommit else ""
    return sqlite3.connect(path, timeout=30, isolation_level=isolation_level)


def backup_via_sqlite_api(src_path: str, dst_path: str) -> None:
    """
    Usa a Backup API do SQLite, que é mais apropriada que cópia simples
    do arquivo quando há possibilidade de o banco estar aberto. [web:18]
    """
    src_conn = _connect(src_path)
    try:
        dst_conn = _connect(dst_path)
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def pragma_check(path: str, pragma_name: str) -> tuple[bool, list[str]]:
    conn = _connect(path)
    try:
        rows = [str(r[0]) for r in conn.execute(f"PRAGMA {pragma_name};").fetchall()]
    finally:
        conn.close()
    ok = len(rows) == 1 and rows[0].strip().lower() == "ok"
    return ok, rows


def quick_check(path: str) -> tuple[bool, list[str]]:
    return pragma_check(path, "quick_check")


def integrity_check(path: str) -> tuple[bool, list[str]]:
    return pragma_check(path, "integrity_check")


def reindex_and_vacuum(path: str) -> None:
    """
    REINDEX pode corrigir inconsistência de índices, e VACUUM reescreve
    o banco em novo layout interno quando o arquivo está utilizável. [web:11]
    """
    conn = _connect(path, autocommit=True)
    try:
        conn.execute("REINDEX;")
        conn.execute("VACUUM;")
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Dump / recover / import
# --------------------------------------------------------------------------


def dump_via_cli(src_path: str, dump_path: str, *, use_recover: bool = False) -> None:
    """
    Gera dump usando o shell sqlite3. .dump e .recover são comandos do
    shell, não SQL da biblioteca. [web:59][web:60]
    """
    command = ".recover" if use_recover else ".dump"
    with open(dump_path, "w", encoding="utf-8", newline="\n") as f:
        result = subprocess.run(
            ["sqlite3", src_path, command],
            stdout=f,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    if result.returncode != 0:
        raise RepairError(f"sqlite3 CLI falhou ({command}): {result.stderr.strip()}")


def dump_via_python(src_path: str, dump_path: str) -> None:
    """
    Fallback Python puro via iterdump(); costuma falhar em corrupções mais
    severas, mas vale a tentativa. [web:18]
    """
    conn = _connect(src_path)
    try:
        with open(dump_path, "w", encoding="utf-8", newline="\n") as f:
            for line in conn.iterdump():
                f.write(line)
                f.write("\n")
    finally:
        conn.close()


def _dump_has_inline_errors(dump_path: str) -> bool:
    """
    O shell pode emitir arquivo com comentários/erros inline e mesmo assim
    encerrar aparentemente sem desastre completo. [web:47][web:65]
    """
    markers = (
        "/**** ERROR:",
        "Error: database disk image is malformed",
        "Error: near line",
        "sql error:",
        "Runtime error near line",
    )
    try:
        with open(dump_path, "r", encoding="utf-8", errors="replace", newline="") as f:
            content = f.read()
    except OSError:
        return False
    return any(m in content for m in markers)


def read_text_file_with_fallbacks(path: str) -> tuple[str, str]:
    """
    Tenta leitura em UTF-8, UTF-8 com BOM, cp1252 e latin-1, nessa ordem.
    Isso evita UnicodeDecodeError em Windows quando o arquivo vier em
    encoding fora do esperado. [web:18]
    """
    encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
    last_error = None

    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                return f.read(), enc
        except UnicodeDecodeError as e:
            last_error = e

    raise RepairError(f"Não foi possível decodificar o dump '{path}': {last_error}")


def sanitize_dump_sql(sql_script: str) -> str:
    """
    Remove meta-comandos do shell SQLite e outras linhas que não são SQL
    executável pela biblioteca sqlite3 do Python. [web:59][web:63]
    """
    cleaned_lines: list[str] = []
    skip_prefixes = (
        ".",
        "sqlite>",
    )

    for raw_line in sql_script.splitlines():
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()

        if not stripped:
            cleaned_lines.append("")
            continue

        if stripped.startswith(skip_prefixes):
            continue

        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    if cleaned:
        cleaned += "\n"
    return cleaned


def build_db_from_dump(dump_path: str, new_db_path: str) -> str:
    """
    Importa o dump para um novo banco e retorna o encoding efetivamente usado.
    """
    if os.path.exists(new_db_path):
        os.remove(new_db_path)

    conn = _connect(new_db_path)
    try:
        sql_script, used_encoding = read_text_file_with_fallbacks(dump_path)
        sql_script = sanitize_dump_sql(sql_script)
        conn.executescript(sql_script)
        conn.commit()
        return used_encoding
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Contagens e preservação de dados
# --------------------------------------------------------------------------


def list_user_tables(path: str) -> list[str]:
    conn = _connect(path)
    try:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def table_row_counts(path: str) -> dict[str, int | None]:
    """
    Faz um inventário best-effort das tabelas legíveis e suas contagens.
    Se uma tabela individual falhar, ela recebe None; isso evita colapsar
    toda a comparação por uma única tabela ruim. [web:11]
    """
    conn = _connect(path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        counts: dict[str, int | None] = {}
        for name in tables:
            try:
                row = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()
                counts[name] = int(row[0]) if row is not None else 0
            except sqlite3.DatabaseError:
                counts[name] = None
        return counts
    finally:
        conn.close()


def detect_data_loss(
    baseline: dict[str, int | None],
    candidate: dict[str, int | None],
) -> tuple[bool, list[str], int]:
    """
    Só acusa perda quando o baseline tinha valor conhecido e o candidato
    ficou ausente/ilegível ou com menos linhas. Tabelas baseline=None são
    ignoradas porque já estavam ilegíveis antes. [web:11]
    """
    problems: list[str] = []
    lost_rows = 0

    for table, baseline_count in baseline.items():
        if baseline_count is None:
            continue

        candidate_count = candidate.get(table)

        if candidate_count is None:
            problems.append(
                f"Tabela '{table}' tinha {baseline_count} linha(s) legíveis antes "
                f"e não existe (ou não foi possível contar) no resultado do reparo."
            )
            lost_rows += baseline_count
        elif candidate_count < baseline_count:
            problems.append(
                f"Tabela '{table}' tinha {baseline_count} linha(s) antes e ficou "
                f"com {candidate_count} depois do reparo."
            )
            lost_rows += (baseline_count - candidate_count)

    return (len(problems) > 0), problems, lost_rows


def total_known_rows(counts: dict[str, int | None]) -> int:
    return sum(v for v in counts.values() if isinstance(v, int))


def _safe_row_counts(path: str, report: RepairReport, label: str) -> dict[str, int | None]:
    try:
        counts = table_row_counts(path)
        report.log(f"Contagem de linhas ({label}): {counts}")
        return counts
    except sqlite3.DatabaseError as e:
        report.log(f"Não foi possível obter contagem de linhas ({label}): {e}")
        return {}


# --------------------------------------------------------------------------
# Export auxiliar opcional
# --------------------------------------------------------------------------


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise RepairError(f"Identificador inválido para exportação: {name!r}")
    return name


def export_readable_tables_to_csv(db_path: str, output_dir: str, report: RepairReport | None = None) -> list[str]:
    """
    Exporta, em modo best-effort, as tabelas legíveis para CSV. Isso não
    repara o banco, mas cria uma trilha extra de salvage antes de decisões
    manuais. [web:11]
    """
    os.makedirs(output_dir, exist_ok=True)
    exported: list[str] = []

    conn = _connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = list_user_tables(db_path)
        for table in tables:
            try:
                safe_table = _safe_identifier(table)
                rows = conn.execute(f'SELECT * FROM "{safe_table}"').fetchall()
                out_path = os.path.join(output_dir, f"{safe_table}.csv")

                with open(out_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    if rows:
                        writer.writerow(rows[0].keys())
                        for row in rows:
                            writer.writerow(list(row))
                    else:
                        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{safe_table}")').fetchall()]
                        writer.writerow(cols)

                exported.append(out_path)
                if report:
                    report.log(f"Tabela exportada para CSV: {out_path}")
            except Exception as e:
                if report:
                    report.log(f"Falha ao exportar tabela '{table}' para CSV: {e}")
    finally:
        conn.close()

    return exported


# --------------------------------------------------------------------------
# Seleção de melhor candidato
# --------------------------------------------------------------------------


def choose_best_candidate(
    baseline_counts: dict[str, int | None],
    candidates: list[CandidateResult],
    report: RepairReport,
) -> CandidateResult:
    """
    Critério:
    1) menor quantidade de linhas perdidas;
    2) menor número de tabelas afetadas;
    3) maior total de linhas conhecidas recuperadas.
    """
    if not candidates:
        raise RepairError("Nenhum candidato disponível para seleção.")

    scored: list[tuple[int, int, int, CandidateResult]] = []

    for candidate in candidates:
        loss, details, lost_rows = detect_data_loss(baseline_counts, candidate.counts)
        candidate.loss_detected = loss
        candidate.loss_details = details
        candidate.lost_rows = lost_rows
        candidate.total_rows = total_known_rows(candidate.counts)

        affected_tables = len(details)
        scored.append((lost_rows, affected_tables, -candidate.total_rows, candidate))

        report.log(
            f"  [{candidate.label}] total de linhas recuperadas: {candidate.total_rows}; "
            f"linhas perdidas: {candidate.lost_rows}; tabelas afetadas: {affected_tables}"
        )

    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    return scored[0][3]


# --------------------------------------------------------------------------
# Orquestração principal
# --------------------------------------------------------------------------


def repair_database(
    db_path: str,
    backup_dir: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    export_csv_dir: str | None = None,
) -> RepairReport:
    """
    Fluxo completo de checagem/reparo.

    Parâmetros:
    - db_path: caminho do banco original.
    - backup_dir: diretório dos backups.
    - dry_run: verifica e relata, sem substituir o original.
    - force: permite substituir mesmo com perda detectada, desde que o
      candidato passe no integrity_check.
    - export_csv_dir: se informado, exporta tabelas legíveis do backup
      corrompido para CSV antes das tentativas mais agressivas.
    """
    report = RepairReport(db_path=os.path.abspath(db_path))

    if not os.path.exists(db_path):
        report.error = f"Arquivo não encontrado: {db_path}"
        return report

    backup_dir = backup_dir or os.path.dirname(os.path.abspath(db_path))
    os.makedirs(backup_dir, exist_ok=True)

    base_name = os.path.basename(db_path)
    backup_path = os.path.join(backup_dir, f"{base_name}.bak_{_timestamp()}")

    report.log(f"Criando backup em {backup_path} (via Connection.backup)")
    try:
        backup_via_sqlite_api(db_path, backup_path)
    except sqlite3.DatabaseError as e:
        report.log(f"Backup via API falhou ({e}); usando cópia de arquivo bruta")
        shutil.copy2(db_path, backup_path)

    report.backup_path = backup_path

    report.log("Rodando PRAGMA quick_check no banco original")
    try:
        q_ok, q_issues = quick_check(db_path)
    except sqlite3.DatabaseError as e:
        q_ok, q_issues = False, [str(e)]

    report.original_quick_ok = q_ok
    report.original_quick_issues = q_issues
    report.log(f"Resultado quick_check: {q_issues[:5]}")

    report.log("Rodando PRAGMA integrity_check no banco original")
    try:
        i_ok, i_issues = integrity_check(db_path)
    except sqlite3.DatabaseError as e:
        i_ok, i_issues = False, [str(e)]

    report.original_ok = i_ok
    report.original_issues = i_issues

    if i_ok:
        report.log("Schema íntegro. Nenhuma ação necessária.")
        report.final_ok = True
        return report

    report.log(f"Problemas detectados: {i_issues[:5]}")

    if dry_run:
        report.log("dry_run=True: parando aqui sem alterar nada.")
        report.final_ok = False
        return report

    baseline_counts = _safe_row_counts(backup_path, report, "baseline, banco corrompido")
    report.baseline_counts = baseline_counts

    if export_csv_dir:
        report.log(f"Exportando tabelas legíveis para CSV em: {export_csv_dir}")
        export_readable_tables_to_csv(backup_path, export_csv_dir, report=report)

    with tempfile.TemporaryDirectory(prefix="sqlite_repair_") as tmp:
        # ------------------------------------------------------------------
        # Estratégia 1: reparo leve
        # ------------------------------------------------------------------
        work_copy = os.path.join(tmp, "work_reindex.db")
        report.log("Tentativa 1: REINDEX + VACUUM em cópia de trabalho")

        try:
            shutil.copy2(backup_path, work_copy)
            reindex_and_vacuum(work_copy)
            ok, issues = integrity_check(work_copy)
        except sqlite3.DatabaseError as e:
            ok, issues = False, [str(e)]

        if ok:
            candidate_counts = _safe_row_counts(work_copy, report, "após REINDEX+VACUUM")
            loss, details, _lost_rows = detect_data_loss(baseline_counts, candidate_counts)

            report.candidate_counts = candidate_counts
            report.data_loss_detected = loss
            report.data_loss_details = details

            if not loss or force:
                report.log(
                    "REINDEX + VACUUM resolveu o problema sem perda de dados detectada."
                    if not loss
                    else "Perda de dados detectada, mas force=True: prosseguindo mesmo assim."
                )
                report.strategy_used = "reindex_vacuum"
                report.forced = bool(loss and force)

                os.replace(work_copy, db_path)
                report.replaced = True
                report.final_ok = True
                return report

            report.log(
                "REINDEX + VACUUM produziu um banco estruturalmente válido, "
                "MAS com menos dados do que o backup — substituição BLOQUEADA."
            )
            for d in details:
                report.log(f"  ! {d}")
        else:
            report.log(f"REINDEX/VACUUM não resolveu: {issues[:5]}")

        # ------------------------------------------------------------------
        # Estratégia 2: reconstrução por múltiplos dumps
        # ------------------------------------------------------------------
        report.log("Tentativa 2: reconstrução completa via dump (testando todas as estratégias)")
        candidates: list[CandidateResult] = []

        def _try_strategy(label: str, dump_fn: Callable[..., None], *dump_args) -> None:
            dump_path = os.path.join(tmp, f"dump_{label}.sql")
            rebuilt_path = os.path.join(tmp, f"rebuilt_{label}.db")

            try:
                dump_fn(*dump_args, dump_path)
            except (RepairError, sqlite3.DatabaseError) as e:
                report.log(f"  [{label}] geração do dump falhou: {e}")
                return

            if _dump_has_inline_errors(dump_path):
                report.log(
                    f"  [{label}] dump gerado, mas contém marcadores de erro inline "
                    f"(a extração provavelmente foi parcial)"
                )

            try:
                used_encoding = build_db_from_dump(dump_path, rebuilt_path)
                ok, issues = integrity_check(rebuilt_path)
            except (RepairError, sqlite3.DatabaseError) as e:
                report.log(f"  [{label}] reconstrução/validação falhou: {e}")
                return

            if not ok:
                report.log(f"  [{label}] banco reconstruído não passou no integrity_check: {issues[:3]}")
                return

            counts = _safe_row_counts(rebuilt_path, report, f"candidato [{label}]")
            report.log(f"  [{label}] dump importado usando encoding: {used_encoding}")

            candidates.append(
                CandidateResult(
                    label=label,
                    db_path=rebuilt_path,
                    counts=counts,
                    imported_dump_encoding=used_encoding,
                )
            )

        if _sqlite_cli_available():
            _try_strategy("dump_cli", lambda src, dst: dump_via_cli(src, dst, use_recover=False), backup_path)
            _try_strategy("recover_cli", lambda src, dst: dump_via_cli(src, dst, use_recover=True), backup_path)
        else:
            report.log("  sqlite3 CLI não encontrado no PATH; pulando .dump/.recover via CLI")

        _try_strategy("iterdump_python", dump_via_python, backup_path)

        if not candidates:
            report.error = (
                "Nenhuma estratégia de reconstrução produziu um banco estruturalmente válido."
            )
            report.log(report.error)
            report.log("Original mantido intocado. Backup preservado para investigação manual.")
            report.final_ok = False
            return report

        best = choose_best_candidate(baseline_counts, candidates, report)

        report.candidate_counts = best.counts
        report.data_loss_detected = best.loss_detected
        report.data_loss_details = best.loss_details
        report.imported_dump_encoding = best.imported_dump_encoding
        report.log(f"Melhor candidato: [{best.label}] (linhas perdidas no total: {best.lost_rows})")

        if not best.loss_detected or force:
            report.log(
                f"Reconstrução via {best.label} resolveu o problema sem perda de dados detectada."
                if not best.loss_detected
                else f"Perda de dados detectada mesmo no melhor candidato ({best.label}), "
                     "mas force=True: prosseguindo mesmo assim."
            )
            report.strategy_used = f"full_rebuild:{best.label}"
            report.forced = bool(best.loss_detected and force)

            os.replace(best.db_path, db_path)
            report.replaced = True
            report.final_ok = True
            return report

        labels = [c.label for c in candidates]
        report.error = (
            f"Nenhuma estratégia de reconstrução (incluindo {labels}) conseguiu "
            "recuperar todos os dados que ainda eram legíveis no backup. "
            f"Melhor resultado obtido: [{best.label}], com perda de dados. "
            "Substituição BLOQUEADA automaticamente. Original mantido intocado; "
            "revise manualmente ou rode novamente com force=True se aceitar perda parcial."
        )
        report.log(report.error)
        for d in best.loss_details:
            report.log(f"  ! {d}")

        report.final_ok = False
        return report