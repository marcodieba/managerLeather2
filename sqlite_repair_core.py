"""
sqlite_repair_core.py

Lógica de recuperação segura para bancos SQLite corrompidos
(ex.: "malformed database schema", "database disk image is malformed").

Princípios de design:

1. O arquivo ORIGINAL nunca é modificado diretamente durante as tentativas
   de reparo. REINDEX, VACUUM e reconstrução via dump rodam sempre em
   cópias de trabalho. A troca do arquivo original só acontece no final,
   via os.replace() (operação atômica no mesmo filesystem).

2. "Estruturalmente válido" NÃO é o mesmo que "dados preservados".
   PRAGMA integrity_check valida a consistência de páginas/índices/b-trees;
   um banco vazio passa nele com "ok" tranquilamente. Por isso, antes de
   qualquer substituição do original, o script exige DUAS aprovações:
     a) integrity_check OK no candidato
     b) contagem de linhas por tabela no candidato >= contagem de linhas
        por tabela que ainda era legível no backup original
   Se (b) falhar — ou seja, se o candidato "reparado" tem menos dados do
   que o que ainda dava para ler do banco corrompido — a substituição é
   BLOQUEADA automaticamente, mesmo que (a) tenha passado. Só prossegue
   com force=True, e mesmo assim com aviso explícito no relatório.

Fluxo:
    1. Backup do original (via sqlite3.Connection.backup, não shutil.copy)
    2. PRAGMA integrity_check no original
       -> OK: nada a fazer
       -> falhou: segue para reparo
    3. Cópia de trabalho -> REINDEX + VACUUM -> integrity_check + contagem
       -> OK e sem perda de dados: substitui o original
       -> falhou ou com perda: segue para reconstrução completa
    4. Dump completo (sqlite3 CLI .dump, ou .recover se disponível,
       ou fallback Python via iterdump) -> novo banco -> integrity_check
       + contagem de linhas
       -> OK e sem perda de dados: substitui o original
       -> falhou ou com perda: mantém original intocado, mantém backup,
          reporta exatamente o que foi/não foi recuperado
"""

from __future__ import annotations

import datetime
import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass, field

logger = logging.getLogger("sqlite_repair")


class RepairError(Exception):
    """Erro fatal durante o processo de reparo (não usado para 'schema ok')."""


@dataclass
class RepairReport:
    db_path: str
    backup_path: str | None = None
    original_ok: bool | None = None
    original_issues: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    strategy_used: str | None = None  # None | "reindex_vacuum" | "full_rebuild"
    final_ok: bool | None = None
    replaced: bool = False
    forced: bool = False
    error: str | None = None

    # Diagnóstico de preservação de dados
    baseline_counts: dict[str, int | None] | None = None
    candidate_counts: dict[str, int | None] | None = None
    data_loss_detected: bool | None = None
    data_loss_details: list[str] = field(default_factory=list)

    def log(self, msg: str):
        logger.info(msg)
        self.steps.append(msg)

    def summary(self) -> str:
        lines = [
            f"Banco: {self.db_path}",
            f"Backup criado em: {self.backup_path}",
            f"Integridade original OK: {self.original_ok}",
        ]
        if self.original_issues and not self.original_ok:
            lines.append(f"Problemas encontrados: {self.original_issues[:5]}")
        if self.strategy_used:
            lines.append(f"Estratégia de reparo usada: {self.strategy_used}")
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
# Utilitários de baixo nível
# --------------------------------------------------------------------------

def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_via_sqlite_api(src_path: str, dst_path: str) -> None:
    """
    Usa a Backup API nativa do sqlite3 (Connection.backup), que é segura
    mesmo com o banco de origem aberto/em uso, ao contrário de shutil.copy.
    """
    src_conn = sqlite3.connect(src_path)
    try:
        dst_conn = sqlite3.connect(dst_path)
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def integrity_check(path: str, quick: bool = False) -> tuple[bool, list[str]]:
    pragma = "quick_check" if quick else "integrity_check"
    conn = sqlite3.connect(path)
    try:
        rows = [r[0] for r in conn.execute(f"PRAGMA {pragma}").fetchall()]
    finally:
        conn.close()
    ok = len(rows) == 1 and rows[0].lower() == "ok"
    return ok, rows


def reindex_and_vacuum(path: str) -> None:
    """Roda REINDEX e VACUUM em modo autocommit (necessário para VACUUM)."""
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        conn.execute("REINDEX")
        conn.execute("VACUUM")
    finally:
        conn.close()


def _sqlite_cli_available() -> bool:
    return shutil.which("sqlite3") is not None


def _dump_has_inline_errors(dump_path: str) -> bool:
    """
    O CLI `sqlite3 arquivo .dump` pode terminar com exit code 0 mesmo tendo
    encontrado corrupção durante a extração — nesse caso ele escreve o erro
    como comentário SQL dentro do próprio dump (ex.: linhas contendo
    "/**** ERROR:" ou "Error: database disk image is malformed") e aborta
    a extração daquele ponto em diante. Isso não derruba o processo, então
    precisamos inspecionar o conteúdo, não só o exit code.
    """
    markers = ("/**** ERROR:", "Error: database disk image is malformed", "Error: near line")
    try:
        with open(dump_path, "r", errors="ignore") as f:
            content = f.read()
    except OSError:
        return False
    return any(m in content for m in markers)


def dump_via_cli(src_path: str, dump_path: str, use_recover: bool = False) -> None:
    """
    Usa o CLI sqlite3 para gerar o dump. Prefere ".recover" quando o schema
    está muito danificado (disponível em SQLite >= 3.29), pois consegue
    extrair dados mesmo quando sqlite_master está corrompido. Cai para
    ".dump" no caso comum.
    """
    command = ".recover" if use_recover else ".dump"
    with open(dump_path, "w") as f:
        result = subprocess.run(
            ["sqlite3", src_path, command],
            stdout=f,
            stderr=subprocess.PIPE,
            text=True,
        )
    if result.returncode != 0:
        raise RepairError(f"sqlite3 CLI falhou ({command}): {result.stderr.strip()}")


def dump_via_python(src_path: str, dump_path: str) -> None:
    """Fallback puro em Python via iterdump(), usado se o CLI não existir."""
    conn = sqlite3.connect(src_path)
    try:
        with open(dump_path, "w") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
    finally:
        conn.close()


def build_db_from_dump(dump_path: str, new_db_path: str) -> None:
    conn = sqlite3.connect(new_db_path)
    try:
        with open(dump_path, "r") as f:
            sql_script = f.read()
        conn.executescript(sql_script)
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Checagem de preservação de dados (o portão de segurança principal)
# --------------------------------------------------------------------------

def table_row_counts(path: str) -> dict[str, int | None]:
    """
    Faz um levantamento best-effort de "quantas linhas existem em cada
    tabela". Não levanta exceção se uma tabela individual falhar ao contar
    (banco parcialmente corrompido) — marca essa tabela como None (contagem
    desconhecida) e segue para as outras. Só levanta exceção se nem a lista
    de tabelas puder ser obtida (schema totalmente ilegível).

    Tabelas internas do SQLite (sqlite_%) são ignoradas.
    """
    conn = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        counts: dict[str, int | None] = {}
        for name in tables:
            try:
                counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except sqlite3.DatabaseError:
                counts[name] = None  # tabela existe mas não deu pra contar
        return counts
    finally:
        conn.close()


def detect_data_loss(
    baseline: dict[str, int | None],
    candidate: dict[str, int | None],
) -> tuple[bool, list[str]]:
    """
    Compara a "foto" de antes (o que ainda era legível no arquivo corrompido)
    com a "foto" de depois (o candidato a substituir o original).

    Regra: qualquer tabela que TINHA uma contagem conhecida no baseline e
    aparece com contagem MENOR (ou ausente) no candidato é reportada como
    perda de dados. Tabelas com contagem desconhecida no baseline (None,
    porque já estavam ilegíveis antes de qualquer reparo) não entram na
    comparação — não tem como culpar o reparo por uma perda que já tinha
    acontecido antes dele.
    """
    problems: list[str] = []

    for table, baseline_count in baseline.items():
        if baseline_count is None:
            continue
        candidate_count = candidate.get(table)
        if candidate_count is None:
            problems.append(
                f"Tabela '{table}' tinha {baseline_count} linha(s) legíveis antes "
                f"e não existe (ou não foi possível contar) no resultado do reparo."
            )
        elif candidate_count < baseline_count:
            problems.append(
                f"Tabela '{table}' tinha {baseline_count} linha(s) antes e ficou "
                f"com {candidate_count} depois do reparo."
            )

    return (len(problems) > 0), problems


# --------------------------------------------------------------------------
# Orquestração principal
# --------------------------------------------------------------------------

def _safe_row_counts(path: str, report: RepairReport, label: str) -> dict[str, int | None]:
    """Wrapper que nunca deixa a contagem derrubar o processo inteiro."""
    try:
        counts = table_row_counts(path)
        report.log(f"Contagem de linhas ({label}): {counts}")
        return counts
    except sqlite3.DatabaseError as e:
        report.log(f"Não foi possível obter contagem de linhas ({label}): {e}")
        return {}


def repair_database(
    db_path: str,
    backup_dir: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> RepairReport:
    """
    Executa o fluxo completo de checagem/reparo descrito no cabeçalho do
    módulo. Retorna um RepairReport com tudo que foi feito.

    force=True ignora o bloqueio por perda de dados detectada (ainda assim
    exige que o integrity_check tenha passado). Use com cautela — é uma
    decisão consciente de aceitar perder o que não deu pra recuperar.
    """
    report = RepairReport(db_path=os.path.abspath(db_path))

    if not os.path.exists(db_path):
        report.error = f"Arquivo não encontrado: {db_path}"
        return report

    backup_dir = backup_dir or os.path.dirname(os.path.abspath(db_path))
    os.makedirs(backup_dir, exist_ok=True)
    base_name = os.path.basename(db_path)
    backup_path = os.path.join(backup_dir, f"{base_name}.bak_{_timestamp()}")

    # 1. Backup sempre, independente do resultado do integrity_check
    report.log(f"Criando backup em {backup_path} (via Connection.backup)")
    try:
        backup_via_sqlite_api(db_path, backup_path)
    except sqlite3.DatabaseError as e:
        report.log(f"Backup via API falhou ({e}); usando cópia de arquivo bruta")
        shutil.copy2(db_path, backup_path)
    report.backup_path = backup_path

    # 2. Integrity check no original
    report.log("Rodando PRAGMA integrity_check no banco original")
    try:
        ok, issues = integrity_check(db_path)
    except sqlite3.DatabaseError as e:
        ok, issues = False, [str(e)]
    report.original_ok = ok
    report.original_issues = issues

    if ok:
        report.log("Schema íntegro. Nenhuma ação necessária.")
        report.final_ok = True
        return report

    report.log(f"Problemas detectados: {issues[:5]}")

    if dry_run:
        report.log("dry_run=True: parando aqui sem alterar nada.")
        return report

    # Baseline: quanto ainda dá pra ler do banco corrompido, ANTES de
    # qualquer tentativa de reparo. É contra isso que vamos comparar.
    baseline_counts = _safe_row_counts(backup_path, report, "baseline, banco corrompido")
    report.baseline_counts = baseline_counts

    with tempfile.TemporaryDirectory(prefix="sqlite_repair_") as tmp:
        # 3. Tentativa leve: REINDEX + VACUUM em uma CÓPIA de trabalho
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
            loss, details = detect_data_loss(baseline_counts, candidate_counts)
            report.candidate_counts = candidate_counts
            report.data_loss_detected = loss

            if not loss or force:
                report.log(
                    "REINDEX + VACUUM resolveu o problema sem perda de dados detectada."
                    if not loss else
                    "Perda de dados detectada, mas force=True: prosseguindo mesmo assim."
                )
                report.strategy_used = "reindex_vacuum"
                report.forced = loss and force
                report.data_loss_details = details
                os.replace(work_copy, db_path)
                report.replaced = True
                report.final_ok = True
                return report
            else:
                report.data_loss_details = details
                report.log(
                    "REINDEX + VACUUM produziu um banco estruturalmente válido, "
                    "MAS com menos dados do que o backup — substituição BLOQUEADA."
                )
                for d in details:
                    report.log(f"  ! {d}")
        else:
            report.log(f"REINDEX/VACUUM não resolveu: {issues[:5]}")

        # 4. Reconstrução completa via dump.
        #
        # IMPORTANTE: o CLI `sqlite3 arquivo .dump` pode terminar com exit
        # code 0 mesmo quando encontrou corrupção durante a extração — ele
        # escreve os erros como comentários SQL dentro do próprio dump e
        # aborta a extração cedo, sem sinalizar falha no processo. Por isso
        # NÃO paramos na primeira tentativa "sem erro de exit code": rodamos
        # todas as estratégias disponíveis (.dump, .recover, iterdump em
        # Python) e ficamos com a que efetivamente preservar mais dados.
        report.log("Tentativa 2: reconstrução completa via dump (testando todas as estratégias)")

        candidates: list[tuple[str, str, dict[str, int | None]]] = []  # (estrategia, path, counts)

        def _try_strategy(label: str, dump_fn, *dump_args) -> None:
            dump_path = os.path.join(tmp, f"dump_{label}.sql")
            new_db_path = os.path.join(tmp, f"rebuilt_{label}.db")
            try:
                dump_fn(*dump_args, dump_path)
            except (RepairError, sqlite3.DatabaseError) as e:
                report.log(f"  [{label}] geração do dump falhou: {e}")
                return

            if _dump_has_inline_errors(dump_path):
                report.log(
                    f"  [{label}] dump gerado (exit ok), mas contém marcadores de erro "
                    f"inline do sqlite3 (corrupção interrompeu a extração)"
                )

            try:
                build_db_from_dump(dump_path, new_db_path)
                ok, issues = integrity_check(new_db_path)
            except sqlite3.DatabaseError as e:
                report.log(f"  [{label}] reconstrução/validação falhou: {e}")
                return

            if not ok:
                report.log(f"  [{label}] banco reconstruído não passou no integrity_check: {issues[:3]}")
                return

            counts = _safe_row_counts(new_db_path, report, f"candidato [{label}]")
            candidates.append((label, new_db_path, counts))

        if _sqlite_cli_available():
            _try_strategy("dump_cli", lambda src, dst: dump_via_cli(src, dst, use_recover=False), backup_path)
            _try_strategy("recover_cli", lambda src, dst: dump_via_cli(src, dst, use_recover=True), backup_path)
        else:
            report.log("  sqlite3 CLI não encontrado no PATH; pulando .dump/.recover via CLI")
        _try_strategy("iterdump_python", dump_via_python, backup_path)

        if not candidates:
            report.error = "Nenhuma estratégia de reconstrução produziu um banco estruturalmente válido."
            report.log(report.error)
            report.log("Original mantido intocado. Backup preservado para investigação manual.")
            report.final_ok = False
            return report

        # Escolhe o candidato com MENOS perda de dados (idealmente zero).
        scored = []
        for label, path, counts in candidates:
            loss, details = detect_data_loss(baseline_counts, counts)
            lost_rows = sum(
                (baseline_counts.get(t) or 0) - (counts.get(t) or 0)
                for t in baseline_counts
                if baseline_counts.get(t) is not None
            )
            scored.append((lost_rows, loss, label, path, counts, details))
            report.log(f"  [{label}] total de linhas recuperadas: {sum(v for v in counts.values() if v)}")

        scored.sort(key=lambda x: x[0])  # menor perda primeiro
        lost_rows, loss, label, new_db_path, candidate_counts, details = scored[0]

        report.candidate_counts = candidate_counts
        report.data_loss_detected = loss
        report.data_loss_details = details
        report.log(f"Melhor candidato: [{label}] (linhas perdidas no total: {lost_rows})")

        if not loss or force:
            report.log(
                f"Reconstrução via {label} resolveu o problema sem perda de dados detectada."
                if not loss else
                f"Perda de dados detectada mesmo no melhor candidato ({label}), "
                "mas force=True: prosseguindo mesmo assim."
            )
            report.strategy_used = f"full_rebuild:{label}"
            report.forced = loss and force
            os.replace(new_db_path, db_path)
            report.replaced = True
            report.final_ok = True
            return report

        report.error = (
            f"Nenhuma estratégia de reconstrução (incluindo {[c[0] for c in candidates]}) "
            "conseguiu recuperar todos os dados que ainda eram legíveis no backup. "
            f"Melhor resultado obtido: [{label}], com perda de dados. Substituição "
            "BLOQUEADA automaticamente. Original mantido intocado; revise manualmente "
            "ou rode novamente com force=True (CLI: --force) se aceitar a perda parcial."
        )
        report.log(report.error)
        for d in details:
            report.log(f"  ! {d}")
        report.final_ok = False
        return report
