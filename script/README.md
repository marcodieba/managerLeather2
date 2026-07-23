# Reparo automático de SQLite

Ferramenta para diagnosticar e recuperar bancos SQLite corrompidos
(`malformed database schema`, `database disk image is malformed`, etc.)
de forma segura, sem risco de piorar a corrupção.

## Arquivos

```
scripts/
├── sqlite_repair_core.py        # lógica de reparo (reutilizável)
├── repair_sqlite.py             # CLI standalone
├── management/
│   └── commands/
│       └── repairdb.py          # comando Django: manage.py repairdb
└── README.md
```

## Princípio de segurança

O arquivo **original nunca é modificado durante as tentativas de reparo**.
`REINDEX`, `VACUUM` e a reconstrução via dump sempre rodam em **cópias de
trabalho** dentro de um diretório temporário. A troca do banco original só
acontece com `os.replace()` (atômico no mesmo filesystem) e **somente se**
a cópia reparada passar no `PRAGMA integrity_check`. Se nada funcionar, o
original fica intocado e o backup é preservado para investigação manual.

## Fluxo

1. Backup via `sqlite3.Connection.backup()` (API nativa — segura mesmo com
   o banco em uso; se ela falhar por causa da própria corrupção, cai para
   `shutil.copy2` como último recurso).
2. `PRAGMA integrity_check` no banco original.
   - OK → nada a fazer.
3. Corrompido → cópia de trabalho → `REINDEX` + `VACUUM` → checa de novo.
   - OK → substitui o original.
4. Ainda corrompido → dump completo (usa `sqlite3` CLI com `.dump`, depois
   `.recover` se disponível, com fallback em Python via `iterdump()`) →
   novo banco → `integrity_check`.
   - OK → substitui o original.
   - Falhou → mantém original intocado, mantém backup, reporta erro.

## Uso — CLI standalone

```bash
python repair_sqlite.py /caminho/para/db.sqlite3
python repair_sqlite.py /caminho/para/db.sqlite3 --backup-dir /caminho/backups
python repair_sqlite.py /caminho/para/db.sqlite3 --dry-run   # só diagnostica
```

Código de saída: `0` se o banco está (ou ficou) íntegro, `1` caso contrário.

## Uso — comando Django

1. Copie `management/commands/repairdb.py` para dentro de um app do seu
   projeto (ex.: `core/management/commands/repairdb.py`), mantendo a
   pasta `management/__init__.py` e `management/commands/__init__.py`.
2. Coloque `sqlite_repair_core.py` num local importável — mais simples é
   copiá-lo para o mesmo diretório de `repairdb.py`.
3. Rode:

```bash
python manage.py repairdb
python manage.py repairdb --database default --backup-dir /caminho/backups
python manage.py repairdb --dry-run
```

## Sobre reparo automático "on-error" (Django)

O ideal é rodar `repairdb` **fora do ciclo de request** — por cron, por um
health check, ou manualmente ao notar o erro — e não dentro do handler que
capturou a exceção. Interceptar `DatabaseError` e disparar o reparo no meio
de uma request é arriscado: outras conexões/threads podem estar acessando
o mesmo arquivo `.sqlite3` naquele instante, e você quer ter controle sobre
*quando* a troca atômica do arquivo acontece. Um padrão razoável:

```python
# em algum job/cron, não dentro da view:
from django.core.management import call_command
call_command("repairdb")
```

Se quiser mesmo um gatilho reativo, encapsule numa tarefa assíncrona
(Celery, etc.) disparada pelo log do erro, nunca de forma síncrona dentro
da própria request que falhou.
