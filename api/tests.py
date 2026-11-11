from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from inscricoes.models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala


def cliente_de(usuario=None):
    cliente = APIClient()
    if usuario is not None:
        token, _ = Token.objects.get_or_create(user=usuario)
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return cliente


class ApiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cadastrar_dados", verbosity=0)
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
        cls.auditorio = Sala.objects.get(nome="Auditório")

    def dados_atividade(self, **alteracoes):
        dados = {
            "evento": self.evento.pk, "titulo": "Nova palestra", "tipo": "PA", "descricao": "Uma palestra.",
            "responsavel": "Maria", "sala": self.auditorio.pk,
            "inicio": "2026-10-21T08:00:00-03:00", "fim": "2026-10-21T09:00:00-03:00",
        }
        dados.update(alteracoes)
        return dados

    def dados_evento(self, **alteracoes):
        dados = {
            "nome": "Mostra de Projetos", "descricao": "Projetos do campus.",
            "data_inicio": "2026-11-10", "data_fim": "2026-11-11",
        }
        dados.update(alteracoes)
        return dados

    def inscrever_no_evento(self, usuario, evento):
        return InscricaoEvento.objects.create(evento=evento, participante=usuario)


class AutenticacaoTests(ApiTestCase):
    def test_token_e_obtido_com_usuario_e_senha(self):
        resposta = APIClient().post(
            "/api/token/", {"username": "participante4", "password": "Eventos@2026"}, format="json"
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["token"], Token.objects.get(user=self.participante).key)

    def test_senha_errada_nao_gera_token(self):
        resposta = APIClient().post(
            "/api/token/", {"username": "participante4", "password": "errada"}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertNotIn("token", resposta.json())

    def test_token_invalido_e_recusado_ate_na_leitura(self):
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION="Token invalido")
        self.assertEqual(cliente.get("/api/eventos/").status_code, 401)

    def test_sessao_do_navegador_nao_autentica_a_api(self):
        cliente = APIClient()
        cliente.force_login(self.organizador)
        resposta = cliente.post("/api/eventos/", self.dados_evento(), format="json")
        self.assertEqual(resposta.status_code, 401)

    def test_leitura_publica_de_salas_eventos_e_atividades(self):
        for caminho in ["/api/salas/", "/api/eventos/", "/api/atividades/"]:
            self.assertEqual(APIClient().get(caminho).status_code, 200)
        self.assertEqual(APIClient().get(f"/api/eventos/{self.evento.pk}/").status_code, 200)
        self.assertEqual(APIClient().get(f"/api/atividades/{self.atividade.pk}/").status_code, 200)

    def test_inscricoes_exigem_token(self):
        cliente = APIClient()
        self.assertEqual(cliente.post("/api/inscricoes/eventos/", {"evento": self.evento.pk}).status_code, 401)
        self.assertEqual(cliente.get("/api/inscricoes/atividades/").status_code, 401)
        self.assertEqual(cliente.delete("/api/inscricoes/atividades/1/").status_code, 401)


class OrganizadorTests(ApiTestCase):
    def test_criar_atividade_sem_token_retorna_401(self):
        resposta = APIClient().post("/api/atividades/", self.dados_atividade(), format="json")
        self.assertEqual(resposta.status_code, 401)

    def test_criar_atividade_como_participante_retorna_403(self):
        resposta = cliente_de(self.participante).post("/api/atividades/", self.dados_atividade(), format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_criar_atividade_como_organizador_retorna_201(self):
        resposta = cliente_de(self.organizador).post("/api/atividades/", self.dados_atividade(), format="json")
        self.assertEqual(resposta.status_code, 201)
        corpo = resposta.json()
        self.assertEqual(corpo["sala_nome"], "Auditório")
        self.assertEqual(corpo["vagas_restantes"], 80)
        self.assertTrue(Atividade.objects.filter(titulo="Nova palestra", evento=self.evento).exists())

    def test_organizador_nao_altera_nem_exclui_o_que_e_de_outro(self):
        cliente = cliente_de(self.outro_organizador)
        self.assertEqual(
            cliente.patch(f"/api/eventos/{self.evento.pk}/", {"nome": "Invadido"}, format="json").status_code, 403
        )
        self.assertEqual(cliente.delete(f"/api/eventos/{self.evento.pk}/").status_code, 403)
        self.assertEqual(
            cliente.patch(f"/api/atividades/{self.atividade.pk}/", {"titulo": "Invadida"}, format="json").status_code,
            403,
        )
        self.assertEqual(cliente.delete(f"/api/atividades/{self.atividade.pk}/").status_code, 403)
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.nome, "Semana de Tecnologia")
        self.assertTrue(Atividade.objects.filter(pk=self.atividade.pk).exists())

    def test_organizador_nao_cria_atividade_em_evento_de_outro(self):
        resposta = cliente_de(self.outro_organizador).post(
            "/api/atividades/", self.dados_atividade(), format="json"
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Atividade.objects.filter(titulo="Nova palestra").exists())

    def test_organizador_altera_e_exclui_o_que_e_seu(self):
        cliente = cliente_de(self.organizador)
        resposta = cliente.patch(f"/api/eventos/{self.fechado.pk}/", {"nome": "Egressos 2026"}, format="json")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["nome"], "Egressos 2026")
        resposta = cliente.patch(f"/api/atividades/{self.seguinte.pk}/", {"titulo": "Projetos"}, format="json")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(cliente.delete(f"/api/atividades/{self.seguinte.pk}/").status_code, 204)
        self.assertEqual(cliente.delete(f"/api/eventos/{self.fechado.pk}/").status_code, 204)
        self.assertFalse(Evento.objects.filter(pk=self.fechado.pk).exists())

    def test_organizador_do_evento_vem_do_token_e_nao_do_corpo(self):
        resposta = cliente_de(self.organizador).post(
            "/api/eventos/", self.dados_evento(organizador=self.outro_organizador.pk), format="json"
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["organizador"], "organizador2")
        self.assertEqual(Evento.objects.get(nome="Mostra de Projetos").organizador, self.organizador)

    def test_participante_nao_cria_evento(self):
        resposta = cliente_de(self.participante).post("/api/eventos/", self.dados_evento(), format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_atividade_com_fim_antes_do_inicio_retorna_400_em_json(self):
        resposta = cliente_de(self.organizador).post(
            "/api/atividades/",
            self.dados_atividade(inicio="2026-10-21T09:00:00-03:00", fim="2026-10-21T08:00:00-03:00"),
            format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"fim": ["O fim precisa ser depois do início."]})

    def test_atividade_em_sala_ocupada_retorna_400_em_json(self):
        resposta = cliente_de(self.organizador).post(
            "/api/atividades/",
            self.dados_atividade(
                sala=self.atividade.sala_id,
                inicio="2026-10-19T09:30:00-03:00", fim="2026-10-19T10:30:00-03:00",
            ),
            format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"sala": ["A sala já está ocupada nesse horário."]})

    def test_atividade_fora_do_periodo_do_evento_retorna_400(self):
        resposta = cliente_de(self.organizador).post(
            "/api/atividades/",
            self.dados_atividade(inicio="2026-10-25T08:00:00-03:00", fim="2026-10-25T09:00:00-03:00"),
            format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("non_field_errors", resposta.json())

    def test_evento_com_periodo_invertido_retorna_400(self):
        resposta = cliente_de(self.organizador).post(
            "/api/eventos/", self.dados_evento(data_inicio="2026-11-12", data_fim="2026-11-10"), format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("data_fim", resposta.json())

    def test_atividade_nao_muda_de_evento(self):
        resposta = cliente_de(self.organizador).patch(
            f"/api/atividades/{self.seguinte.pk}/", {"evento": self.fechado.pk}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"evento": ["Uma atividade não pode mudar de evento."]})

    def test_alteracao_que_conflita_com_agenda_de_inscrito_retorna_400(self):
        resposta = cliente_de(self.organizador).patch(
            f"/api/atividades/{self.seguinte.pk}/", {"inicio": "2026-10-19T09:00:00-03:00"}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)

    def test_vagas_na_resposta_acompanham_a_sala_apos_a_alteracao(self):
        atividade = Atividade.objects.get(titulo="Django na prática")
        resposta = cliente_de(self.organizador).patch(
            f"/api/atividades/{atividade.pk}/",
            {"sala": Sala.objects.get(nome="Laboratório de Informática").pk,
             "inicio": "2026-10-20T09:00:00-03:00", "fim": "2026-10-20T10:00:00-03:00"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["vagas_restantes"], 24)


class InscricaoEventoTests(ApiTestCase):
    def test_participante_se_inscreve_no_evento(self):
        resposta = cliente_de(self.outro_participante).post(
            "/api/inscricoes/eventos/", {"evento": self.outro_evento.pk}, format="json"
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["participante"], "participante5")
        self.assertTrue(
            InscricaoEvento.objects.filter(evento=self.outro_evento, participante=self.outro_participante).exists()
        )

    def test_participante_do_corpo_e_ignorado(self):
        resposta = cliente_de(self.outro_participante).post(
            "/api/inscricoes/eventos/",
            {"evento": self.outro_evento.pk, "participante": self.participante.pk}, format="json",
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(
            InscricaoEvento.objects.get(evento=self.outro_evento, participante=self.outro_participante).pk,
            resposta.json()["id"],
        )

    def test_nova_inscricao_no_mesmo_evento_retorna_400(self):
        resposta = cliente_de(self.participante).post(
            "/api/inscricoes/eventos/", {"evento": self.evento.pk}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"non_field_errors": ["Você já está inscrito neste evento."]})
        self.assertEqual(InscricaoEvento.objects.filter(evento=self.evento, participante=self.participante).count(), 1)

    def test_evento_com_inscricoes_fechadas_retorna_400(self):
        resposta = cliente_de(self.participante).post(
            "/api/inscricoes/eventos/", {"evento": self.fechado.pk}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"non_field_errors": ["As inscrições deste evento estão fechadas."]})

    def test_evento_inexistente_retorna_400(self):
        resposta = cliente_de(self.participante).post("/api/inscricoes/eventos/", {"evento": 999}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("evento", resposta.json())

    def test_lista_traz_apenas_as_inscricoes_de_quem_pediu(self):
        resposta = cliente_de(self.participante).get("/api/inscricoes/eventos/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual({item["participante"] for item in resposta.json()["results"]}, {"participante4"})
        self.assertEqual(resposta.json()["count"], 2)

    def test_cancelar_inscricao_no_evento_remove_as_das_atividades(self):
        inscricao = InscricaoEvento.objects.get(evento=self.evento, participante=self.participante)
        self.assertEqual(inscricao.inscricoes_atividades.count(), 1)
        resposta = cliente_de(self.participante).delete(f"/api/inscricoes/eventos/{inscricao.pk}/")
        self.assertEqual(resposta.status_code, 204)
        self.assertFalse(InscricaoEvento.objects.filter(pk=inscricao.pk).exists())
        self.assertFalse(InscricaoAtividade.objects.filter(atividade=self.atividade, inscricao_evento_id=inscricao.pk).exists())
        resposta = cliente_de(self.participante).get(f"/api/atividades/{self.atividade.pk}/")
        self.assertEqual(resposta.json()["vagas_restantes"], 2)

    def test_cancelar_inscricao_de_outra_pessoa_retorna_403(self):
        inscricao = InscricaoEvento.objects.get(evento=self.evento, participante=self.participante)
        resposta = cliente_de(self.outro_participante).delete(f"/api/inscricoes/eventos/{inscricao.pk}/")
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(InscricaoEvento.objects.filter(pk=inscricao.pk).exists())

    def test_cancelar_inscricao_inexistente_retorna_404(self):
        self.assertEqual(cliente_de(self.participante).delete("/api/inscricoes/eventos/999/").status_code, 404)
        self.assertEqual(cliente_de(self.participante).delete("/api/inscricoes/eventos/abc/").status_code, 404)


class InscricaoAtividadeTests(ApiTestCase):
    def inscrever(self, usuario, atividade):
        return cliente_de(usuario).post(
            "/api/inscricoes/atividades/", {"atividade": atividade.pk}, format="json"
        )

    def vagas(self, atividade):
        return APIClient().get(f"/api/atividades/{atividade.pk}/").json()["vagas_restantes"]

    def test_inscricao_em_atividade_sem_estar_no_evento_retorna_400(self):
        resposta = self.inscrever(self.terceiro, self.atividade)
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(
            resposta.json(), {"non_field_errors": ["Inscreva-se no evento antes de escolher uma atividade."]}
        )
        self.assertEqual(self.vagas(self.atividade), 1)

    def test_inscricao_com_vaga_retorna_201_e_reduz_as_vagas(self):
        self.assertEqual(self.vagas(self.seguinte), 2)
        resposta = self.inscrever(self.outro_participante, self.seguinte)
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(self.vagas(self.seguinte), 1)

    def test_ocupar_a_ultima_vaga_e_tentar_mais_uma_retorna_400(self):
        self.inscrever_no_evento(self.terceiro, self.evento)
        self.assertEqual(self.inscrever(self.outro_participante, self.atividade).status_code, 201)
        self.assertEqual(self.vagas(self.atividade), 0)
        resposta = self.inscrever(self.terceiro, self.atividade)
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"non_field_errors": ["Esta atividade está lotada."]})
        self.assertEqual(self.vagas(self.atividade), 0)

    def test_atividade_simultanea_no_mesmo_evento_retorna_400(self):
        resposta = self.inscrever(self.participante, self.conflito_interno)
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(
            resposta.json(), {"non_field_errors": ["Esta atividade conflita com outra inscrição na sua agenda."]}
        )

    def test_atividade_simultanea_em_outro_evento_retorna_400(self):
        resposta = self.inscrever(self.participante, self.conflito_externo)
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(
            resposta.json(), {"non_field_errors": ["Esta atividade conflita com outra inscrição na sua agenda."]}
        )

    def test_atividades_consecutivas_nao_conflitam(self):
        self.assertEqual(self.inscrever(self.participante, self.seguinte).status_code, 201)

    def test_inscricao_repetida_na_atividade_retorna_400(self):
        resposta = self.inscrever(self.participante, self.atividade)
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"non_field_errors": ["Você já está inscrito nesta atividade."]})

    def test_atividade_inexistente_retorna_400(self):
        resposta = cliente_de(self.participante).post("/api/inscricoes/atividades/", {"atividade": 999}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("atividade", resposta.json())

    def test_cancelar_inscricao_na_atividade_devolve_a_vaga(self):
        inscricao = InscricaoAtividade.objects.get(
            atividade=self.atividade, inscricao_evento__participante=self.participante
        )
        self.assertEqual(self.vagas(self.atividade), 1)
        resposta = cliente_de(self.participante).delete(f"/api/inscricoes/atividades/{inscricao.pk}/")
        self.assertEqual(resposta.status_code, 204)
        self.assertEqual(self.vagas(self.atividade), 2)
        self.assertTrue(InscricaoEvento.objects.filter(participante=self.participante, evento=self.evento).exists())

    def test_cancelar_inscricao_de_outra_pessoa_retorna_403(self):
        inscricao = InscricaoAtividade.objects.get(
            atividade=self.atividade, inscricao_evento__participante=self.participante
        )
        resposta = cliente_de(self.outro_participante).delete(f"/api/inscricoes/atividades/{inscricao.pk}/")
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(InscricaoAtividade.objects.filter(pk=inscricao.pk).exists())

    def test_lista_traz_apenas_as_inscricoes_de_quem_pediu(self):
        resposta = cliente_de(self.outro_participante).get("/api/inscricoes/atividades/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["count"], 0)
        resposta = cliente_de(self.participante).get("/api/inscricoes/atividades/")
        self.assertEqual(resposta.json()["count"], 2)


class ConcorrenciaApiTests(TransactionTestCase):
    def setUp(self):
        call_command("cadastrar_dados", verbosity=0)

    def enviar_juntos(self, envios):
        barreira = Barrier(len(envios))

        def enviar(envio):
            close_old_connections()
            try:
                usuario, caminho, dados = envio
                cliente = cliente_de(usuario)
                barreira.wait(timeout=10)
                return cliente.post(caminho, dados, format="json").status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(envios)) as executor:
            return list(executor.map(enviar, envios))

    def test_dois_envios_nao_ocupam_a_mesma_ultima_vaga(self):
        atividade = Atividade.objects.get(titulo="Django na prática")
        quinto = User.objects.get(username="participante5")
        sexto = User.objects.create_user(username="participante6", password="Eventos@2026")
        InscricaoEvento.objects.create(evento=atividade.evento, participante=sexto)
        envios = [(usuario, "/api/inscricoes/atividades/", {"atividade": atividade.pk}) for usuario in (quinto, sexto)]
        self.assertEqual(sorted(self.enviar_juntos(envios)), [201, 400])
        self.assertEqual(atividade.inscricoes.count(), 2)

    def test_envios_simultaneos_respeitam_agenda_entre_eventos(self):
        usuario = User.objects.create_user(username="participante6", password="Eventos@2026")
        atividades = [Atividade.objects.get(titulo=titulo) for titulo in ["Django na prática", "Pesquisa e inovação"]]
        for atividade in atividades:
            InscricaoEvento.objects.create(evento=atividade.evento, participante=usuario)
        envios = [(usuario, "/api/inscricoes/atividades/", {"atividade": atividade.pk}) for atividade in atividades]
        self.assertEqual(sorted(self.enviar_juntos(envios)), [201, 400])
        self.assertEqual(InscricaoAtividade.objects.filter(inscricao_evento__participante=usuario).count(), 1)

# novos testes

from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from django.urls import reverse

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

Usuario = get_user_model()

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def data_hora(dia: int, hora: int, minuto: int = 0) -> datetime:
    """
    Cria um datetime compatível com a configuração USE_TZ do Django.
    """
    valor = datetime(2026, 11, dia, hora, minuto)

    if timezone.is_aware(timezone.now()):
        return timezone.make_aware(
            valor,
            timezone.get_current_timezone()
        )

    return valor

class BaseAPITestCase(APITestCase):
    """
    Classe-base dos testes da API.

    Centraliza:
    - Usuários;
    - Tokens;
    - Salas;
    - Evento e atividade iniciais;
    - Métodos auxiliares para autenticação e criação de dados.
    """

    @classmethod
    def setUpTestData(cls):

        # -----------------------------
        # Usuários
        # -----------------------------

        cls.organizador = Usuario.objects.create_user(
            username="organizador_api",
            email="organizador@example.test",
            password="senha-teste-123",
        )

        cls.outro_organizador = Usuario.objects.create_user(
            username="outro_organizador_api",
            email="outro.organizador@example.test",
            password="senha-teste-123",
        )

        cls.participante_a = Usuario.objects.create_user(
            username="participante_api_a",
            email="participante.a@example.test",
            password="senha-teste-123",
        )

        cls.participante_b = Usuario.objects.create_user(
            username="participante_api_b",
            email="participante.b@example.test",
            password="senha-teste-123",
        )

        cls.participante_c = Usuario.objects.create_user(
            username="participante_api_c",
            email="participante.c@example.test",
            password="senha-teste-123",
        )

        # -----------------------------
        # Permissão de organizador
        # -----------------------------

        permissao = Permission.objects.get(
            codename="organizar_eventos",
            content_type__app_label="inscricoes",
            content_type__model="evento",
        )

        cls.organizador.user_permissions.add(permissao)
        cls.outro_organizador.user_permissions.add(permissao)

        # -----------------------------
        # Tokens
        # -----------------------------

        cls.token_organizador = Token.objects.create(
            user=cls.organizador
        )

        cls.token_outro_organizador = Token.objects.create(
            user=cls.outro_organizador
        )

        cls.token_participante_a = Token.objects.create(
            user=cls.participante_a
        )

        cls.token_participante_b = Token.objects.create(
            user=cls.participante_b
        )

        cls.token_participante_c = Token.objects.create(
            user=cls.participante_c
        )

        # -----------------------------
        # Salas
        # -----------------------------

        cls.sala = Sala.objects.create(
            nome="Laboratório API",
            bloco="Bloco A",
            capacidade=2,
        )

        cls.sala_alternativa = Sala.objects.create(
            nome="Sala Alternativa API",
            bloco="Bloco B",
            capacidade=3,
        )

        # -----------------------------
        # Evento
        # -----------------------------

        cls.evento = Evento.objects.create(
            nome="Semana de Tecnologia - API",
            descricao="Evento utilizado nos testes da API.",
            data_inicio=date(2026, 11, 10),
            data_fim=date(2026, 11, 12),
            inscricoes_abertas=True,
            organizador=cls.organizador,
        )

        # -----------------------------
        # Atividade
        # -----------------------------

        cls.atividade = Atividade.objects.create(
            evento=cls.evento,
            titulo="Introdução à API REST",
            tipo=Atividade.Tipo.PALESTRA,
            descricao="Atividade pública para os testes.",
            responsavel="Equipe de teste",
            sala=cls.sala,
            inicio=data_hora(10, 9),
            fim=data_hora(10, 10),
        )

    # ========================================================
    # MÉTODOS AUXILIARES
    # ========================================================

    def autenticar(self, token: Token):
        """Autentica o cliente usando Token Authentication."""
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )

    def inscrever_no_evento(self, participante):
        """Cria uma inscrição diretamente no banco para preparar o teste."""
        return InscricaoEvento.objects.create(
            evento=self.evento,
            participante=participante,
        )

    def criar_atividade(
        self,
        *,
        titulo,
        sala=None,
        inicio=None,
        fim=None,
    ):
        """Cria uma atividade para ser utilizada nos testes."""

        inicio = inicio or data_hora(10, 11)
        fim = fim or (inicio + timedelta(hours=1))

        return Atividade.objects.create(
            evento=self.evento,
            titulo=titulo,
            tipo=Atividade.Tipo.TREINAMENTO,
            descricao=f"Descrição de {titulo}.",
            responsavel="Responsável de teste",
            sala=sala or self.sala_alternativa,
            inicio=inicio,
            fim=fim,
        )

    def url_inscrever_evento(self):
        return reverse(
            "api:inscricao-evento-list"
        )


    def url_inscrever_atividade(self):
        return reverse(
            "api:inscricao-atividade-list"
        )


# ============================================================
# RF2 E RF3 — REGRAS DE NEGÓCIO PELA API
# ============================================================

class APIRegraDeNegocioTest(BaseAPITestCase):
    """
    Verifica as cinco regras de negócio através dos endpoints REST.

    Cada regra é exercitada pelos caminhos permitidos e recusados.
    """

    # --------------------------------------------------------
    # REGRA 1 — Inscrições não ultrapassam a capacidade da sala
    # --------------------------------------------------------

    def test_inscricao_em_atividade_com_vaga_e_permitida(self):
        self.inscrever_no_evento(self.participante_a)
        self.autenticar(self.token_participante_a)

        resposta = self.client.post(
            self.url_inscrever_atividade(),
            data={"atividade": self.atividade.pk},
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_201_CREATED,
            resposta.data,
        )

        self.assertTrue(
            InscricaoAtividade.objects.filter(
                inscricao_evento__participante=self.participante_a,
                atividade=self.atividade,
            ).exists()
        )

    def test_inscricao_em_atividade_lotada_e_recusada(self):
        inscricao_a = self.inscrever_no_evento(self.participante_a)
        inscricao_b = self.inscrever_no_evento(self.participante_b)

        # A sala possui capacidade para duas pessoas.
        InscricaoAtividade.objects.create(
            inscricao_evento=inscricao_a,
            atividade=self.atividade,
        )

        InscricaoAtividade.objects.create(
            inscricao_evento=inscricao_b,
            atividade=self.atividade,
        )

        self.inscrever_no_evento(self.participante_c)
        self.autenticar(self.token_participante_c)

        resposta = self.client.post(
            self.url_inscrever_atividade(),
            data={"atividade": self.atividade.pk},
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        # A terceira inscrição não deve ser persistida.
        self.assertEqual(
            self.atividade.inscricoes.count(),
            2,
        )

        self.assertFalse(
            self.atividade.inscricoes.filter(
                inscricao_evento__participante=self.participante_c
            ).exists()
        )

    # --------------------------------------------------------
    # REGRA 2 — Participante não pode ter atividades simultâneas
    # --------------------------------------------------------

    def test_participante_pode_se_inscrever_em_atividade_sem_conflito(self):
        atividade_seguinte = self.criar_atividade(
            titulo="Atividade sem conflito",
            sala=self.sala_alternativa,
            inicio=data_hora(10, 10),
            fim=data_hora(10, 11),
        )

        inscricao_evento = self.inscrever_no_evento(
            self.participante_a
        )

        InscricaoAtividade.objects.create(
            inscricao_evento=inscricao_evento,
            atividade=self.atividade,
        )

        self.autenticar(self.token_participante_a)

        resposta = self.client.post(
            self.url_inscrever_atividade(),
            data={"atividade": atividade_seguinte.pk},
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_201_CREATED,
            resposta.data,
        )

        self.assertTrue(
            atividade_seguinte.inscricoes.filter(
                inscricao_evento__participante=self.participante_a
            ).exists()
        )

    def test_participante_nao_pode_se_inscrever_em_atividade_com_horario_sobreposto(self):
        atividade_conflitante = self.criar_atividade(
            titulo="Atividade com conflito",
            sala=self.sala_alternativa,
            inicio=data_hora(10, 9, 30),
            fim=data_hora(10, 10, 30),
        )

        inscricao_evento = self.inscrever_no_evento(
            self.participante_a
        )

        InscricaoAtividade.objects.create(
            inscricao_evento=inscricao_evento,
            atividade=self.atividade,
        )

        self.autenticar(self.token_participante_a)

        resposta = self.client.post(
            self.url_inscrever_atividade(),
            data={"atividade": atividade_conflitante.pk},
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        # A inscrição original continua sendo a única existente.
        self.assertEqual(
            InscricaoAtividade.objects.filter(
                inscricao_evento=inscricao_evento
            ).count(),
            1,
        )

    # --------------------------------------------------------
    # REGRA 3 — Não pode haver atividades simultâneas na sala
    # --------------------------------------------------------

    def test_api_permite_atividade_na_mesma_sala_em_horario_livre(self):
        self.autenticar(self.token_organizador)

        payload = {
            "evento": self.evento.pk,
            "titulo": "Atividade posterior na mesma sala",
            "tipo": Atividade.Tipo.PALESTRA,
            "descricao": "Horário sem conflito.",
            "responsavel": "Responsável",
            "sala": self.sala.pk,
            "inicio": data_hora(10, 10).isoformat(),
            "fim": data_hora(10, 11).isoformat(),
        }

        resposta = self.client.post(
            reverse("api:atividade-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_201_CREATED,
            resposta.data,
        )

        self.assertTrue(
            Atividade.objects.filter(
                titulo="Atividade posterior na mesma sala"
            ).exists()
        )

    def test_api_recusa_duas_atividades_na_mesma_sala_em_horarios_sobrepostos(self):
        self.autenticar(self.token_organizador)

        quantidade_inicial = Atividade.objects.count()

        payload = {
            "evento": self.evento.pk,
            "titulo": "Atividade com sala já ocupada",
            "tipo": Atividade.Tipo.TREINAMENTO,
            "descricao": "Tentativa de conflito de sala.",
            "responsavel": "Responsável",
            "sala": self.sala.pk,
            "inicio": data_hora(10, 9, 30).isoformat(),
            "fim": data_hora(10, 10, 30).isoformat(),
        }

        resposta = self.client.post(
            reverse("api:atividade-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            Atividade.objects.count(),
            quantidade_inicial,
        )

    # --------------------------------------------------------
    # REGRA 4 — Só pode escolher atividade quem está no evento
    # --------------------------------------------------------

    def test_participante_inscrito_no_evento_pode_se_inscrever_em_atividade(self):
        self.inscrever_no_evento(self.participante_a)
        self.autenticar(self.token_participante_a)

        resposta = self.client.post(
            self.url_inscrever_atividade(),
            data={"atividade": self.atividade.pk},
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_201_CREATED,
            resposta.data,
        )

        self.assertTrue(
            InscricaoAtividade.objects.filter(
                inscricao_evento__participante=self.participante_a,
                atividade=self.atividade,
            ).exists()
        )

    def test_participante_nao_inscrito_no_evento_nao_pode_escolher_atividade(self):
        self.autenticar(self.token_participante_a)

        resposta = self.client.post(
            self.url_inscrever_atividade(),
            data={"atividade": self.atividade.pk},
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            InscricaoAtividade.objects.count(),
            0,
        )

    # --------------------------------------------------------
    # REGRA 5 — Cancelar evento remove inscrições nas atividades
    # --------------------------------------------------------

    def test_cancelar_inscricao_no_evento_cancela_inscricoes_das_atividades(self):
        atividade_a = self.criar_atividade(
            titulo="Atividade para cancelamento A",
            inicio=data_hora(10, 11),
            fim=data_hora(10, 12),
        )

        atividade_b = self.criar_atividade(
            titulo="Atividade para cancelamento B",
            inicio=data_hora(10, 12),
            fim=data_hora(10, 13),
        )

        inscricao_evento = self.inscrever_no_evento(
            self.participante_a
        )

        InscricaoAtividade.objects.create(
            inscricao_evento=inscricao_evento,
            atividade=atividade_a,
        )

        InscricaoAtividade.objects.create(
            inscricao_evento=inscricao_evento,
            atividade=atividade_b,
        )

        self.autenticar(self.token_participante_a)

        resposta = self.client.delete(
            reverse(
                "api:inscricao-evento-detail",
                kwargs={"pk": inscricao_evento.pk},
            )
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_204_NO_CONTENT,
        )

        self.assertFalse(
            InscricaoEvento.objects.filter(
                pk=inscricao_evento.pk
            ).exists()
        )

        # on_delete=models.CASCADE deve remover as inscrições relacionadas.
        self.assertFalse(
            InscricaoAtividade.objects.filter(
                atividade__in=[atividade_a, atividade_b]
            ).exists()
        )


# ============================================================
# RF4 — VALIDAÇÃO DOS MODELS PELA API
# ============================================================

class APIValidacaoTest(BaseAPITestCase):
    """
    Verifica se a API recusa dados que violam as validações
    executadas pelos models através de ModeloValidado.save().
    """

    def setUp(self):
        self.autenticar(self.token_organizador)

    def test_api_recusa_evento_com_data_final_anterior_a_inicial(self):
        payload = {
            "nome": "Evento com período inválido",
            "descricao": "A data final é anterior à inicial.",
            "data_inicio": "2026-11-12",
            "data_fim": "2026-11-10",
            "inscricoes_abertas": True,
        }

        resposta = self.client.post(
            reverse("api:evento-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_400_BAD_REQUEST,
            resposta.data,
        )

        self.assertFalse(
            Evento.objects.filter(
                nome="Evento com período inválido"
            ).exists()
        )

    def test_api_recusa_atividade_com_fim_anterior_ao_inicio(self):
        payload = {
            "evento": self.evento.pk,
            "titulo": "Atividade com intervalo inválido",
            "tipo": Atividade.Tipo.PALESTRA,
            "descricao": "O fim ocorre antes do início.",
            "responsavel": "Responsável",
            "sala": self.sala_alternativa.pk,
            "inicio": data_hora(10, 10).isoformat(),
            "fim": data_hora(10, 9).isoformat(),
        }

        resposta = self.client.post(
            reverse("api:atividade-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_400_BAD_REQUEST,
            resposta.data,
        )

        self.assertFalse(
            Atividade.objects.filter(
                titulo="Atividade com intervalo inválido"
            ).exists()
        )

    def test_api_recusa_atividade_fora_do_periodo_do_evento(self):
        payload = {
            "evento": self.evento.pk,
            "titulo": "Atividade fora do período",
            "tipo": Atividade.Tipo.TREINAMENTO,
            "descricao": "A atividade ocorre após o término do evento.",
            "responsavel": "Responsável",
            "sala": self.sala_alternativa.pk,
            "inicio": data_hora(13, 9).isoformat(),
            "fim": data_hora(13, 10).isoformat(),
        }

        resposta = self.client.post(
            reverse("api:atividade-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_400_BAD_REQUEST,
            resposta.data,
        )

        self.assertFalse(
            Atividade.objects.filter(
                titulo="Atividade fora do período"
            ).exists()
        )


# ============================================================
# RF10 — API PÚBLICA E SABOTAGEM 8
# ============================================================

class APIPublicaTest(BaseAPITestCase):
    """
    Verifica os endpoints públicos e os campos disponibilizados
    pelos serializers.
    """

    def test_lista_de_eventos_e_publica_e_retorna_dados_esperados(self):
        resposta = self.client.get(
            reverse("api:evento-list")
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_200_OK,
        )

        eventos = resposta.data["results"]

        evento = next(
            item
            for item in eventos
            if item["id"] == self.evento.pk
        )

        self.assertEqual(
            evento["nome"],
            self.evento.nome,
        )

        self.assertEqual(
            set(evento.keys()),
            {
                "id",
                "nome",
                "descricao",
                "data_inicio",
                "data_fim",
                "inscricoes_abertas",
                "organizador",
            },
        )

        self.assertEqual(
            evento["organizador"],
            self.organizador.username,
        )

        self.assertNotIn("organizador_id", evento)
        self.assertNotIn("email", evento)
        self.assertNotIn("participante", evento)

def test_detalhe_publico_retorna_programacao_sem_dados_privados(self):
    resposta = self.client.get(
        reverse(
            "api:programacao-evento",
            kwargs={"evento_id": self.evento.pk},
        )
    )

    self.assertEqual(
        resposta.status_code,
        status.HTTP_200_OK,
    )

    # A resposta contém evento e atividades.
    self.assertEqual(
        set(resposta.data.keys()),
        {
            "evento",
            "atividades",
        },
    )

    # Verifica os dados públicos do evento.
    evento = resposta.data["evento"]

    self.assertEqual(
        evento["nome"],
        self.evento.nome,
    )

    self.assertEqual(
        set(evento.keys()),
        {
            "id",
            "nome",
            "descricao",
            "data_inicio",
            "data_fim",
            "inscricoes_abertas",
            "organizador",
        },
    )

    self.assertEqual(
        evento["organizador"],
        self.organizador.username,
    )

    self.assertNotIn("organizador_id", evento)
    self.assertNotIn("email", evento)
    self.assertNotIn("participante", evento)

    # Verifica as atividades da programação.
    self.assertEqual(
        len(resposta.data["atividades"]),
        1,
    )

    atividade = resposta.data["atividades"][0]

    self.assertEqual(
        atividade["titulo"],
        self.atividade.titulo,
    )

    self.assertEqual(
        atividade["sala_nome"],
        self.sala.nome,
    )

    self.assertEqual(
        set(atividade.keys()),
        {
            "id",
            "evento",
            "titulo",
            "tipo",
            "descricao",
            "responsavel",
            "sala",
            "sala_nome",
            "inicio",
            "fim",
            "vagas_restantes",
        },
    )

    self.assertNotIn("email", atividade)
    self.assertNotIn("participante", atividade)
    self.assertNotIn("inscricoes", atividade)

    def test_lista_de_atividades_e_publica(self):
        resposta = self.client.get(
            reverse("api:atividade-list")
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_200_OK,
        )

        atividades = resposta.data["results"]

        atividade = next(
            item
            for item in atividades
            if item["id"] == self.atividade.pk
        )

        self.assertEqual(
            atividade["sala_nome"],
            self.sala.nome,
        )

        self.assertEqual(
            set(atividade.keys()),
            {
                "id",
                "evento",
                "titulo",
                "tipo",
                "descricao",
                "responsavel",
                "sala",
                "sala_nome",
                "inicio",
                "fim",
                "vagas_restantes",
            },
        )

        self.assertNotIn("email", atividade)
        self.assertNotIn("participante", atividade)
        self.assertNotIn("inscricoes", atividade)

    def test_consulta_de_salas_e_publica(self):
        resposta = self.client.get(
            reverse("api:sala-list")
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_200_OK,
        )

        salas = resposta.data["results"]

        self.assertTrue(
            any(
                item["nome"] == self.sala.nome
                for item in salas
            )
        )


# ============================================================
# RF11 — API PROTEGIDA
# ============================================================

class APIProtegidaTest(BaseAPITestCase):
    """
    Testa autenticação e autorização das operações protegidas.
    """

    def test_endpoint_protegido_sem_token_responde_401(self):
        payload = {
            "nome": "Evento sem token",
            "descricao": "Não deve ser criado.",
            "data_inicio": "2026-11-10",
            "data_fim": "2026-11-12",
            "inscricoes_abertas": True,
        }

        resposta = self.client.post(
            reverse("api:evento-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self.assertFalse(
            Evento.objects.filter(
                nome="Evento sem token"
            ).exists()
        )

    def test_agenda_sem_token_retorna_401(self):
        resposta = self.client.get(
            reverse("api:agenda-participante")
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_token_invalido_retorna_401(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token token-invalido"
        )

        resposta = self.client.get(
            reverse("api:agenda-participante")
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_usuario_autenticado_sem_permissao_nao_cria_evento(self):
        self.autenticar(self.token_participante_a)

        payload = {
            "nome": "Evento de participante",
            "descricao": "Não deve ser criado.",
            "data_inicio": "2026-11-10",
            "data_fim": "2026-11-12",
            "inscricoes_abertas": True,
        }

        resposta = self.client.post(
            reverse("api:evento-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertFalse(
            Evento.objects.filter(
                nome="Evento de participante"
            ).exists()
        )

    def test_participante_nao_pode_criar_atividade(self):
        self.autenticar(self.token_participante_a)

        quantidade_inicial = Atividade.objects.count()

        payload = {
            "evento": self.evento.pk,
            "titulo": "Atividade de participante",
            "tipo": Atividade.Tipo.PALESTRA,
            "descricao": "Não deve ser criada.",
            "responsavel": "Participante",
            "sala": self.sala_alternativa.pk,
            "inicio": data_hora(10, 11).isoformat(),
            "fim": data_hora(10, 12).isoformat(),
        }

        resposta = self.client.post(
            reverse("api:atividade-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertEqual(
            Atividade.objects.count(),
            quantidade_inicial,
        )

    def test_token_do_organizador_permite_criar_evento(self):
        self.autenticar(self.token_organizador)

        payload = {
            "nome": "Evento criado pela API",
            "descricao": "Criação autorizada.",
            "data_inicio": "2026-11-10",
            "data_fim": "2026-11-12",
            "inscricoes_abertas": True,
        }

        resposta = self.client.post(
            reverse("api:evento-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_201_CREATED,
            resposta.data,
        )

        self.assertTrue(
            Evento.objects.filter(
                nome="Evento criado pela API",
                organizador=self.organizador,
            ).exists()
        )

    def test_participante_autenticado_pode_se_inscrever_no_evento(self):
        self.autenticar(self.token_participante_a)

        resposta = self.client.post(
            self.url_inscrever_evento(),
            data={"evento": self.evento.pk},
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_201_CREATED,
            resposta.data,
        )

        self.assertTrue(
            InscricaoEvento.objects.filter(
                evento=self.evento,
                participante=self.participante_a,
            ).exists()
        )

    def test_organizador_nao_edita_evento_de_outro(self):
        nome_original = self.evento.nome

        self.autenticar(
            self.token_outro_organizador
        )

        resposta = self.client.patch(
            reverse(
                "api:evento-detail",
                kwargs={"pk": self.evento.pk},
            ),
            data={
                "nome": "Nome alterado indevidamente"
            },
            format="json",
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.evento.refresh_from_db()

        self.assertEqual(
            self.evento.nome,
            nome_original,
        )

    def test_usuario_nao_cancela_inscricao_de_outra_pessoa(self):
        inscricao = self.inscrever_no_evento(
            self.participante_a
        )

        self.autenticar(
            self.token_participante_b
        )

        resposta = self.client.delete(
            reverse(
                "api:inscricao-evento-detail",
                kwargs={"pk": inscricao.pk},
            )
        )

        self.assertEqual(
            resposta.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        # O registro original deve permanecer intacto.
        self.assertTrue(
            InscricaoEvento.objects.filter(
                pk=inscricao.pk
            ).exists()
        )


# ============================================================
# RF12 — CONSULTAS AO BANCO
# ============================================================

class APIConsultasTest(BaseAPITestCase):
    """
    Verifica se a consulta da programação pública mantém
    um número constante de consultas ao banco.

    O objetivo é evitar o problema N+1.
    """

    def test_programacao_publica_usa_numero_fixo_de_consultas(self):
        url = reverse(
            "api:programacao-evento",
            kwargs={"evento_id": self.evento.pk},
        )

        # ------------------------------------------
        # Cenário 1: somente uma atividade
        # ------------------------------------------

        with self.assertNumQueries(2):
            resposta_pequena = self.client.get(url)

        self.assertEqual(
            resposta_pequena.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(resposta_pequena.data["atividades"]),
            1,
        )

        # ------------------------------------------
        # Cenário 2: onze atividades
        # ------------------------------------------

        for indice in range(10):
            inicio = data_hora(10, 11 + indice)

            self.criar_atividade(
                titulo=f"Atividade adicional {indice + 1}",
                sala=self.sala_alternativa,
                inicio=inicio,
                fim=inicio + timedelta(minutes=30),
            )

        with self.assertNumQueries(2):
            resposta_grande = self.client.get(url)

        self.assertEqual(
            resposta_grande.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(resposta_grande.data["atividades"]),
            11,
        )
