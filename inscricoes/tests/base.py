from datetime import date, datetime
from io import StringIO

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from inscricoes.models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala


def horario(hora, minuto=0, dia=4):
    return timezone.make_aware(datetime(2030, 3, dia, hora, minuto))


def criar_participante(nome):
    return User.objects.create_user(username=nome, password="Senha@2030")


def criar_organizador(nome):
    usuario = criar_participante(nome)
    usuario.user_permissions.add(Permission.objects.get(codename="organizar_eventos"))
    return usuario


def criar_sala(nome, capacidade):
    return Sala.objects.create(nome=nome, bloco="A", capacidade=capacidade)


def criar_evento(organizador, nome="Feira do Campus", **alteracoes):
    dados = {"descricao": "Evento de teste.", "data_inicio": date(2030, 3, 4), "data_fim": date(2030, 3, 6)}
    dados.update(alteracoes)
    return Evento.objects.create(nome=nome, organizador=organizador, **dados)


def criar_atividade(evento, sala, titulo, inicio, fim):
    return Atividade.objects.create(
        evento=evento, sala=sala, titulo=titulo, tipo=Atividade.Tipo.PALESTRA,
        descricao="Atividade de teste.", responsavel="Joana", inicio=inicio, fim=fim,
    )


def inscrever(participante, evento):
    return InscricaoEvento.objects.create(evento=evento, participante=participante)


def ocupar(inscricao, atividade):
    return InscricaoAtividade.objects.create(inscricao_evento=inscricao, atividade=atividade)


def cliente_de(usuario=None):
    cliente = APIClient()
    if usuario is not None:
        token, _ = Token.objects.get_or_create(user=usuario)
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return cliente


def mensagens(resposta):
    return [str(mensagem) for mensagem in resposta.context["messages"]]


def cadastrar_dados():
    call_command("cadastrar_dados", stdout=StringIO())


class CenarioRegras(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizador = criar_organizador("organizadora")
        cls.outro_organizador = criar_organizador("outra_organizadora")
        cls.participante = criar_participante("ana")
        cls.colega = criar_participante("bia")
        cls.sem_inscricao = criar_participante("carla")
        cls.sala = criar_sala("Sala 1", 1)
        cls.outra_sala = criar_sala("Sala 2", 10)
        cls.evento = criar_evento(cls.organizador)
        cls.outro_evento = criar_evento(cls.outro_organizador, nome="Mostra de Artes")
        cls.atividade = criar_atividade(cls.evento, cls.sala, "Oficina de Git", horario(9), horario(10))
        cls.simultanea = criar_atividade(cls.evento, cls.outra_sala, "Palestra de Redes", horario(9, 30), horario(10, 30))
        cls.seguinte = criar_atividade(cls.evento, cls.outra_sala, "Mesa de Carreira", horario(10, 30), horario(11, 30))
        cls.de_outro_evento = criar_atividade(cls.outro_evento, cls.outra_sala, "Sarau", horario(14), horario(15))
        cls.inscricao = inscrever(cls.participante, cls.evento)
        cls.inscricao_colega = inscrever(cls.colega, cls.evento)


class DadosDeCadastro(TestCase):
    @classmethod
    def setUpTestData(cls):
        cadastrar_dados()
        cls.organizador = User.objects.get(username="organizador2")
        cls.outro_organizador = User.objects.get(username="organizador3")
        cls.participante = User.objects.get(username="participante4")
        cls.outro_participante = User.objects.get(username="participante5")
        cls.terceiro = User.objects.create_user(username="participante6", password="Eventos@2026")
        cls.evento = Evento.objects.get(nome="Semana de Tecnologia")
        cls.outro_evento = Evento.objects.get(nome="Jornada Científica")
        cls.fechado = Evento.objects.get(nome="Encontro de Egressos")
        cls.atividade = Atividade.objects.get(titulo="Django na prática")
        cls.seguinte = Atividade.objects.get(titulo="Apresentação de projetos")
        cls.conflito_interno = Atividade.objects.get(titulo="Acessibilidade na web")
        cls.conflito_externo = Atividade.objects.get(titulo="Pesquisa e inovação")
        cls.posterior = Atividade.objects.get(titulo="Comunicação científica")
        cls.auditorio = Sala.objects.get(nome="Auditório")
        cls.inscricao = InscricaoEvento.objects.get(evento=cls.evento, participante=cls.participante)
