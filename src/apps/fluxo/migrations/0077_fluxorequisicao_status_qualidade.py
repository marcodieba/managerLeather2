from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('fluxo', '0076_operacao_qualidade_genealogia'),
    ]

    operations = [
        migrations.AddField(
            model_name='fluxorequisicao',
            name='status_qualidade',
            field=models.CharField(
                choices=[
                    ('APROVADO', 'Aprovado'),
                    ('BLOQUEADO', 'Bloqueado'),
                    ('REPROCESSO', 'Reprocesso'),
                    ('REFUGO', 'Refugo'),
                ],
                default='APROVADO',
                max_length=20,
            ),
        ),
    ]
