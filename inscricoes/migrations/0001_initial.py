import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Evento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=150, verbose_name='Nome')),
                ('descricao', models.TextField(verbose_name='Descrição')),
                ('data_inicio', models.DateField(verbose_name='Data de início')),
                ('data_fim', models.DateField(verbose_name='Data de fim')),
                ('inscricoes_abertas', models.BooleanField(default=True, verbose_name='Inscrições abertas')),
                ('organizador', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='eventos_organizados', to=settings.AUTH_USER_MODEL, verbose_name='Organizador')),
            ],
            options={
                'ordering': ['data_inicio', 'nome'],
                'permissions': [('organizar_eventos', 'Pode organizar eventos e atividades')],
            },
        ),
        migrations.CreateModel(
            name='Atividade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=150, verbose_name='Título')),
                ('tipo', models.CharField(choices=[('PA', 'Palestra'), ('TR', 'Treinamento'), ('AP', 'Apresentação')], max_length=2, verbose_name='Tipo')),
                ('descricao', models.TextField(verbose_name='Descrição')),
                ('responsavel', models.CharField(max_length=120, verbose_name='Responsável')),
                ('inicio', models.DateTimeField(verbose_name='Início')),
                ('fim', models.DateTimeField(verbose_name='Fim')),
                ('evento', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='atividades', to='inscricoes.evento', verbose_name='Evento')),
            ],
            options={
                'ordering': ['inicio', 'titulo'],
            },
        ),
        migrations.CreateModel(
            name='InscricaoEvento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.DateTimeField(auto_now_add=True, verbose_name='Data de inscrição')),
                ('evento', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inscricoes', to='inscricoes.evento', verbose_name='Evento')),
                ('participante', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inscricoes_eventos', to=settings.AUTH_USER_MODEL, verbose_name='Participante')),
            ],
            options={
                'verbose_name': 'Inscrição no evento',
                'verbose_name_plural': 'Inscrições nos eventos',
                'ordering': ['data', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='InscricaoAtividade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.DateTimeField(auto_now_add=True, verbose_name='Data de inscrição')),
                ('atividade', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inscricoes', to='inscricoes.atividade', verbose_name='Atividade')),
                ('inscricao_evento', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inscricoes_atividades', to='inscricoes.inscricaoevento', verbose_name='Inscrição no evento')),
            ],
            options={
                'verbose_name': 'Inscrição em atividade',
                'verbose_name_plural': 'Inscrições em atividades',
                'ordering': ['atividade__inicio', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='Sala',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, unique=True, verbose_name='Nome')),
                ('bloco', models.CharField(max_length=60, verbose_name='Bloco')),
                ('capacidade', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)], verbose_name='Capacidade')),
            ],
            options={
                'ordering': ['nome'],
                'constraints': [models.CheckConstraint(condition=models.Q(('capacidade__gte', 1)), name='sala_capacidade_positiva')],
            },
        ),
        migrations.AddField(
            model_name='atividade',
            name='sala',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='atividades', to='inscricoes.sala', verbose_name='Sala'),
        ),
        migrations.AddConstraint(
            model_name='evento',
            constraint=models.CheckConstraint(condition=models.Q(('data_fim__gte', models.F('data_inicio'))), name='evento_periodo_valido'),
        ),
        migrations.AddConstraint(
            model_name='inscricaoevento',
            constraint=models.UniqueConstraint(fields=('evento', 'participante'), name='inscricao_evento_unica'),
        ),
        migrations.AddConstraint(
            model_name='inscricaoatividade',
            constraint=models.UniqueConstraint(fields=('inscricao_evento', 'atividade'), name='inscricao_atividade_unica'),
        ),
        migrations.AddConstraint(
            model_name='atividade',
            constraint=models.CheckConstraint(condition=models.Q(('fim__gt', models.F('inicio'))), name='atividade_intervalo_valido'),
        ),
    ]
