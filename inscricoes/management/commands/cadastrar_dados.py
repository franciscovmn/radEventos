from datetime import date, datetime

from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from inscricoes.models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala


class Command(BaseCommand):
    help = "Cadastra as contas, os tokens e a programação de teste sem apagar os dados existentes."

    @transaction.atomic
    def handle(self, *args, **options):
        grupo, _ = Group.objects.get_or_create(name="Organizadores")
        grupo.permissions.add(Permission.objects.get(
            content_type__app_label="inscricoes", codename="organizar_eventos"
        ))
        contas = {}
        for nome in ["admin", "organizador2", "organizador3", "participante4", "participante5"]:
            usuario = User.objects.filter(username=nome).first()
            if usuario is None:
                criar = User.objects.create_superuser if nome == "admin" else User.objects.create_user
                usuario = criar(username=nome, password="Eventos@2026")
            if nome.startswith("organizador"):
                usuario.groups.add(grupo)
            Token.objects.get_or_create(user=usuario)
            contas[nome] = usuario

        pequena, _ = Sala.objects.get_or_create(
            nome="Sala 101", defaults={"bloco": "A", "capacidade": 2}
        )
        laboratorio, _ = Sala.objects.get_or_create(
            nome="Laboratório de Informática", defaults={"bloco": "B", "capacidade": 25}
        )
        auditorio, _ = Sala.objects.get_or_create(
            nome="Auditório", defaults={"bloco": "C", "capacidade": 80}
        )
        semana, _ = Evento.objects.get_or_create(
            nome="Semana de Tecnologia",
            defaults={
                "descricao": "Três dias de encontros sobre desenvolvimento web, projetos e acessibilidade.",
                "data_inicio": date(2026, 10, 19),
                "data_fim": date(2026, 10, 21),
                "organizador": contas["organizador2"],
            },
        )
        jornada, _ = Evento.objects.get_or_create(
            nome="Jornada Científica",
            defaults={
                "descricao": "Compartilhamento de pesquisas e experiências da comunidade acadêmica.",
                "data_inicio": date(2026, 10, 19),
                "data_fim": date(2026, 10, 20),
                "organizador": contas["organizador3"],
            },
        )
        Evento.objects.get_or_create(
            nome="Encontro de Egressos",
            defaults={
                "descricao": "Encontro com ex-alunos do campus. As inscrições já foram encerradas.",
                "data_inicio": date(2026, 10, 22),
                "data_fim": date(2026, 10, 22),
                "inscricoes_abertas": False,
                "organizador": contas["organizador2"],
            },
        )

        atividades = [
            (semana, "Django na prática", Atividade.Tipo.TREINAMENTO, pequena, 19, 9, 0, 10, 0, "Ana Souza", "Criação de uma aplicação web com Django."),
            (semana, "Apresentação de projetos", Atividade.Tipo.APRESENTACAO, pequena, 19, 10, 0, 11, 0, "Bruno Lima", "Projetos desenvolvidos pelos estudantes do campus."),
            (semana, "Acessibilidade na web", Atividade.Tipo.PALESTRA, laboratorio, 19, 9, 30, 10, 30, "Carla Santos", "Como construir páginas que mais pessoas conseguem usar."),
            (jornada, "Pesquisa e inovação", Atividade.Tipo.PALESTRA, auditorio, 19, 9, 0, 10, 0, "Daniel Costa", "Experiências de pesquisa e inovação no campus."),
            (jornada, "Comunicação científica", Atividade.Tipo.TREINAMENTO, auditorio, 20, 14, 0, 15, 0, "Elisa Rocha", "Preparação e apresentação de trabalhos científicos."),
        ]
        cadastradas = {}
        for evento, titulo, tipo, sala, dia, hi, mi, hf, mf, responsavel, descricao in atividades:
            atividade, _ = Atividade.objects.get_or_create(
                evento=evento, titulo=titulo,
                defaults={
                    "tipo": tipo, "sala": sala, "responsavel": responsavel, "descricao": descricao,
                    "inicio": timezone.make_aware(datetime(2026, 10, dia, hi, mi)),
                    "fim": timezone.make_aware(datetime(2026, 10, dia, hf, mf)),
                },
            )
            cadastradas[titulo] = atividade

        inscricao_semana, _ = InscricaoEvento.objects.get_or_create(
            evento=semana, participante=contas["participante4"]
        )
        inscricao_jornada, _ = InscricaoEvento.objects.get_or_create(
            evento=jornada, participante=contas["participante4"]
        )
        InscricaoEvento.objects.get_or_create(evento=semana, participante=contas["participante5"])
        InscricaoAtividade.objects.get_or_create(
            inscricao_evento=inscricao_semana, atividade=cadastradas["Django na prática"]
        )
        InscricaoAtividade.objects.get_or_create(
            inscricao_evento=inscricao_jornada, atividade=cadastradas["Comunicação científica"]
        )
        self.stdout.write(self.style.SUCCESS("Contas, tokens, salas, eventos e atividades cadastrados."))
