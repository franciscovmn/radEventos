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
