from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('fluxo', '0075_movimentacaoproducao'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='movimentacaoproducao',
            name='chave_operacao',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='movimentacaoproducao',
            name='status_qualidade',
            field=models.CharField(
                choices=[('APROVADO', 'Aprovado'), ('BLOQUEADO', 'Bloqueado'),
                         ('REPROCESSO', 'Reprocesso'), ('REFUGO', 'Refugo')],
                default='APROVADO', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='movimentacaoproducao', name='lote_pai',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='movimentacaoproducao', name='lote_filho',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='movimentacaoproducao', name='quantidade_kg',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='movimentacaoproducao', name='quantidade_m2',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='movimentacaoproducao', name='operacao',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='movimentacoes_operacao', to='fluxo.processo'),
        ),
        migrations.CreateModel(
            name='QualidadeMovimentacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[('APROVADO', 'Aprovado'), ('BLOQUEADO', 'Bloqueado'),
                             ('REPROCESSO', 'Reprocesso'), ('REFUGO', 'Refugo')],
                    default='APROVADO', max_length=20)),
                ('justificativa', models.TextField(blank=True, default='')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('autorizado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='autorizacoes_qualidade', to=settings.AUTH_USER_MODEL)),
                ('movimentacao', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name='auditorias_qualidade', to='fluxo.movimentacaoproducao')),
                ('requisicao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='auditorias_qualidade', to='fluxo.requisicao')),
            ],
            options={'ordering': ['-criado_em', '-id']},
        ),
        migrations.CreateModel(
            name='GenealogiaLote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lote_pai', models.CharField(max_length=100)),
                ('lote_filho', models.CharField(max_length=100)),
                ('quantidade_pecas', models.BigIntegerField(blank=True, null=True)),
                ('quantidade_kg', models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True)),
                ('quantidade_m2', models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('movimentacao', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name='genealogias_lote', to='fluxo.movimentacaoproducao')),
                ('operacao', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='genealogias_lote', to='fluxo.processo')),
                ('requisicao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='genealogias_lote', to='fluxo.requisicao')),
            ],
            options={'ordering': ['-criado_em', '-id']},
        ),
    ]
