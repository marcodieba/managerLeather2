from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('fluxo', '0074_requisicao_numero_os'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MovimentacaoProducao',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('quantidade', models.BigIntegerField()),
                ('origens', models.JSONField(default=list)),
                ('motivo', models.CharField(blank=True, default='', max_length=50)),
                ('observacao', models.TextField(blank=True, default='')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                (
                    'operador',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='movimentacoes_producao',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'processo_destino',
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='movimentacoes_destino',
                        to='fluxo.processo',
                    ),
                ),
                (
                    'requisicao',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='movimentacoes_producao',
                        to='fluxo.requisicao',
                    ),
                ),
            ],
            options={
                'ordering': ['-criado_em', '-id'],
            },
        ),
    ]
