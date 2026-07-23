"""
Comando Django: python manage.py clean_orphans [--delete]

Analisa TODOS os models de TODAS as apps do projeto.
Procura por Chaves Estrangeiras (ForeignKeys) inválidas (que apontam para IDs inexistentes devido a corrupção/perda de dados).

Acção:
- Se o campo ForeignKey permitir nulos (null=True), define-o como NULL.
- Se o campo ForeignKey NÃO permitir nulos (null=False), apaga o registo órfão.
"""

from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import connection, transaction
from django.db.models import ForeignKey, OneToOneField


class Command(BaseCommand):
    help = "Varre todos os models procurando por ForeignKeys apontando para IDs que não existem e corrige-os."

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Executa efectivamente as alterações (SET NULL ou DELETE). Sem isto, apenas mostra o que faria.',
        )

    def handle(self, *args, **options):
        is_dry_run = not options['delete']
        if is_dry_run:
            self.stdout.write(self.style.WARNING("Modo de Pré-visualização (Dry-Run). Nada será alterado. Use --delete para corrigir."))
        else:
            self.stdout.write(self.style.WARNING("Modo de Execução. Os registos órfãos serão corrigidos/apagados."))

        total_orphans_found = 0
        total_deleted = 0
        total_nulled = 0

        # Obtém todos os models do projecto
        models = apps.get_models()
        
        for model in models:
            # Pula models do sistema ou de apps de terceiros se quiser, mas aqui verificamos todos
            table_name = model._meta.db_table
            
            # Procura por campos ForeignKey ou OneToOneField
            for field in model._meta.fields:
                if isinstance(field, (ForeignKey, OneToOneField)):
                    fk_column = field.column
                    parent_table = field.related_model._meta.db_table
                    parent_pk = field.related_model._meta.pk.column
                    
                    # Query para encontrar os órfãos usando Raw SQL para maior velocidade
                    query = f"""
                        SELECT id 
                        FROM {table_name}
                        WHERE {fk_column} IS NOT NULL 
                          AND {fk_column} NOT IN (SELECT {parent_pk} FROM {parent_table})
                    """
                    
                    try:
                        with connection.cursor() as cursor:
                            cursor.execute(query)
                            orphans = [row[0] for row in cursor.fetchall()]
                            
                        if orphans:
                            count = len(orphans)
                            total_orphans_found += count
                            self.stdout.write(self.style.ERROR(
                                f"\n[{model._meta.app_label}.{model.__name__}] Campo '{field.name}' "
                                f"tem {count} registos apontando para '{parent_table}' que não existem!"
                            ))

                            if not is_dry_run:
                                with transaction.atomic():
                                    with connection.cursor() as cursor:
                                        if field.null:
                                            # Se permite NULL, vamos limpar a referência
                                            self.stdout.write(f"  -> Definindo {fk_column} = NULL para {count} registos...")
                                            placeholders = ','.join(['%s'] * count)
                                            cursor.execute(f"""
                                                UPDATE {table_name} 
                                                SET {fk_column} = NULL 
                                                WHERE id IN ({placeholders})
                                            """, orphans)
                                            total_nulled += count
                                        else:
                                            # Se não permite NULL, temos de apagar o registo inteiro
                                            self.stdout.write(f"  -> Apagando {count} registos órfãos (campo não aceita nulos)...")
                                            placeholders = ','.join(['%s'] * count)
                                            cursor.execute(f"""
                                                DELETE FROM {table_name} 
                                                WHERE id IN ({placeholders})
                                            """, orphans)
                                            total_deleted += count
                            else:
                                if field.null:
                                    self.stdout.write(f"  -> (Dry Run) Definiria {fk_column} = NULL para {count} registos.")
                                else:
                                    self.stdout.write(f"  -> (Dry Run) Apagaria {count} registos inteiros (campo não aceita nulos).")

                    except Exception as e:
                        # Tabelas não geridas ou que não existem fisicamente podem dar erro
                        pass

        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(
            f"RESUMO: Foram encontrados {total_orphans_found} registos órfãos."
        ))
        
        if not is_dry_run:
            self.stdout.write(self.style.SUCCESS(f"  - Registos apagados: {total_deleted}"))
            self.stdout.write(self.style.SUCCESS(f"  - Registos limpos (NULL): {total_nulled}"))
            self.stdout.write("Agora pode executar 'python manage.py migrate' sem problemas!")
