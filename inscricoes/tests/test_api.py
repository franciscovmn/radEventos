from datetime import date, datetime, timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from inscricoes.models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala

from .base import (
    DadosDeCadastro, cliente_de, criar_atividade, criar_evento, criar_organizador, criar_participante, criar_sala,
    inscrever,
)


CAMPOS_SALA = {"id", "nome", "bloco", "capacidade"}
CAMPOS_EVENTO = {"id", "nome", "descricao", "data_inicio", "data_fim", "inscricoes_abertas", "organizador"}
CAMPOS_ATIVIDADE = {
    "id", "evento", "titulo", "tipo", "descricao", "responsavel",
    "sala", "sala_nome", "inicio", "fim", "vagas_restantes",
}


def url(nome, *args):
    return reverse(f"api:{nome}", args=args)


def data_hora(dia, hora, minuto=0):
    return timezone.make_aware(datetime(2026, 11, dia, hora, minuto))


class ApiComDadosDeCadastro(DadosDeCadastro):
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


class AutenticacaoTests(ApiComDadosDeCadastro):
    def test_token_e_obtido_com_usuario_e_senha(self):
        resposta = APIClient().post(
            url("token"), {"username": "participante4", "password": "Eventos@2026"}, format="json"
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["token"], Token.objects.get(user=self.participante).key)

    def test_senha_errada_nao_gera_token(self):
        resposta = APIClient().post(url("token"), {"username": "participante4", "password": "errada"}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertNotIn("token", resposta.json())

    def test_token_invalido_e_recusado_ate_na_leitura(self):
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION="Token invalido")
        self.assertEqual(cliente.get(url("evento-list")).status_code, 401)

    def test_sessao_do_navegador_nao_autentica_a_api(self):
        cliente = APIClient()
        cliente.force_login(self.organizador)
        resposta = cliente.post(url("evento-list"), self.dados_evento(), format="json")
        self.assertEqual(resposta.status_code, 401)

    def test_leitura_publica_de_salas_eventos_e_atividades(self):
        for endereco in [url("sala-list"), url("evento-list"), url("atividade-list")]:
            self.assertEqual(APIClient().get(endereco).status_code, 200)
        self.assertEqual(APIClient().get(url("evento-detail", self.evento.pk)).status_code, 200)
        self.assertEqual(APIClient().get(url("atividade-detail", self.atividade.pk)).status_code, 200)

    def test_inscricoes_exigem_token(self):
        cliente = APIClient()
        self.assertEqual(cliente.post(url("inscricao-evento-list"), {"evento": self.evento.pk}).status_code, 401)
        self.assertEqual(cliente.get(url("inscricao-atividade-list")).status_code, 401)
        self.assertEqual(cliente.delete(url("inscricao-atividade-detail", 1)).status_code, 401)


class OrganizadorTests(ApiComDadosDeCadastro):
    def test_criar_atividade_sem_token_retorna_401(self):
        resposta = APIClient().post(url("atividade-list"), self.dados_atividade(), format="json")
        self.assertEqual(resposta.status_code, 401)
        self.assertFalse(Atividade.objects.filter(titulo="Nova palestra").exists())

    def test_criar_atividade_como_participante_retorna_403(self):
        resposta = cliente_de(self.participante).post(url("atividade-list"), self.dados_atividade(), format="json")
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Atividade.objects.filter(titulo="Nova palestra").exists())

    def test_criar_atividade_como_organizador_retorna_201(self):
        resposta = cliente_de(self.organizador).post(url("atividade-list"), self.dados_atividade(), format="json")
        self.assertEqual(resposta.status_code, 201)
        corpo = resposta.json()
        self.assertEqual(corpo["sala_nome"], "Auditório")
        self.assertEqual(corpo["vagas_restantes"], 80)
        self.assertTrue(Atividade.objects.filter(titulo="Nova palestra", evento=self.evento).exists())

    def test_organizador_nao_altera_nem_exclui_o_que_e_de_outro(self):
        cliente = cliente_de(self.outro_organizador)
        self.assertEqual(
            cliente.patch(url("evento-detail", self.evento.pk), {"nome": "Invadido"}, format="json").status_code, 403
        )
        self.assertEqual(cliente.delete(url("evento-detail", self.evento.pk)).status_code, 403)
        self.assertEqual(
            cliente.patch(url("atividade-detail", self.atividade.pk), {"titulo": "Invadida"}, format="json").status_code,
            403,
        )
        self.assertEqual(cliente.delete(url("atividade-detail", self.atividade.pk)).status_code, 403)
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.nome, "Semana de Tecnologia")
        self.assertTrue(Atividade.objects.filter(pk=self.atividade.pk).exists())

    def test_organizador_nao_cria_atividade_em_evento_de_outro(self):
        resposta = cliente_de(self.outro_organizador).post(url("atividade-list"), self.dados_atividade(), format="json")
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Atividade.objects.filter(titulo="Nova palestra").exists())

    def test_organizador_altera_e_exclui_o_que_e_seu(self):
        cliente = cliente_de(self.organizador)
        resposta = cliente.patch(url("evento-detail", self.fechado.pk), {"nome": "Egressos 2026"}, format="json")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["nome"], "Egressos 2026")
        resposta = cliente.patch(url("atividade-detail", self.seguinte.pk), {"titulo": "Projetos"}, format="json")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(cliente.delete(url("atividade-detail", self.seguinte.pk)).status_code, 204)
        self.assertEqual(cliente.delete(url("evento-detail", self.fechado.pk)).status_code, 204)
        self.assertFalse(Evento.objects.filter(pk=self.fechado.pk).exists())

    def test_organizador_do_evento_vem_do_token_e_nao_do_corpo(self):
        resposta = cliente_de(self.organizador).post(
            url("evento-list"), self.dados_evento(organizador=self.outro_organizador.pk), format="json"
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["organizador"], "organizador2")
        self.assertEqual(Evento.objects.get(nome="Mostra de Projetos").organizador, self.organizador)

    def test_participante_nao_cria_evento(self):
        resposta = cliente_de(self.participante).post(url("evento-list"), self.dados_evento(), format="json")
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Evento.objects.filter(nome="Mostra de Projetos").exists())

    def test_atividade_com_fim_antes_do_inicio_retorna_400_em_json(self):
        resposta = cliente_de(self.organizador).post(
            url("atividade-list"),
            self.dados_atividade(inicio="2026-10-21T09:00:00-03:00", fim="2026-10-21T08:00:00-03:00"),
            format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"fim": ["O fim precisa ser depois do início."]})

    def test_atividade_em_sala_ocupada_retorna_400_em_json(self):
        resposta = cliente_de(self.organizador).post(
            url("atividade-list"),
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
            url("atividade-list"),
            self.dados_atividade(inicio="2026-10-25T08:00:00-03:00", fim="2026-10-25T09:00:00-03:00"),
            format="json",
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("non_field_errors", resposta.json())

    def test_evento_com_periodo_invertido_retorna_400(self):
        resposta = cliente_de(self.organizador).post(
            url("evento-list"), self.dados_evento(data_inicio="2026-11-12", data_fim="2026-11-10"), format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("data_fim", resposta.json())

    def test_atividade_nao_muda_de_evento(self):
        resposta = cliente_de(self.organizador).patch(
            url("atividade-detail", self.seguinte.pk), {"evento": self.fechado.pk}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"evento": ["Uma atividade não pode mudar de evento."]})

    def test_alteracao_que_conflita_com_agenda_de_inscrito_retorna_400(self):
        resposta = cliente_de(self.organizador).patch(
            url("atividade-detail", self.seguinte.pk), {"inicio": "2026-10-19T09:00:00-03:00"}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)

    def test_vagas_na_resposta_acompanham_a_sala_apos_a_alteracao(self):
        resposta = cliente_de(self.organizador).patch(
            url("atividade-detail", self.atividade.pk),
            {"sala": Sala.objects.get(nome="Laboratório de Informática").pk,
             "inicio": "2026-10-20T09:00:00-03:00", "fim": "2026-10-20T10:00:00-03:00"},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["vagas_restantes"], 24)


class InscricaoEventoTests(ApiComDadosDeCadastro):
    def test_participante_se_inscreve_no_evento(self):
        resposta = cliente_de(self.outro_participante).post(
            url("inscricao-evento-list"), {"evento": self.outro_evento.pk}, format="json"
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["participante"], "participante5")
        self.assertTrue(
            InscricaoEvento.objects.filter(evento=self.outro_evento, participante=self.outro_participante).exists()
        )

    def test_participante_do_corpo_e_ignorado(self):
        resposta = cliente_de(self.outro_participante).post(
            url("inscricao-evento-list"),
            {"evento": self.outro_evento.pk, "participante": self.participante.pk}, format="json",
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(
            InscricaoEvento.objects.get(evento=self.outro_evento, participante=self.outro_participante).pk,
            resposta.json()["id"],
        )

    def test_nova_inscricao_no_mesmo_evento_retorna_400(self):
        resposta = cliente_de(self.participante).post(
            url("inscricao-evento-list"), {"evento": self.evento.pk}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"non_field_errors": ["Você já está inscrito neste evento."]})
        self.assertEqual(InscricaoEvento.objects.filter(evento=self.evento, participante=self.participante).count(), 1)

    def test_evento_com_inscricoes_fechadas_retorna_400(self):
        resposta = cliente_de(self.participante).post(
            url("inscricao-evento-list"), {"evento": self.fechado.pk}, format="json"
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(resposta.json(), {"non_field_errors": ["As inscrições deste evento estão fechadas."]})

    def test_evento_inexistente_retorna_400(self):
        resposta = cliente_de(self.participante).post(url("inscricao-evento-list"), {"evento": 999}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("evento", resposta.json())

    def test_lista_traz_apenas_as_inscricoes_de_quem_pediu(self):
        resposta = cliente_de(self.participante).get(url("inscricao-evento-list"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual({item["participante"] for item in resposta.json()["results"]}, {"participante4"})
        self.assertEqual(resposta.json()["count"], 2)

    def test_cancelar_inscricao_no_evento_remove_as_das_atividades(self):
        self.assertEqual(self.inscricao.inscricoes_atividades.count(), 1)
        resposta = cliente_de(self.participante).delete(url("inscricao-evento-detail", self.inscricao.pk))
        self.assertEqual(resposta.status_code, 204)
        self.assertFalse(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())
        self.assertFalse(
            InscricaoAtividade.objects.filter(atividade=self.atividade, inscricao_evento_id=self.inscricao.pk).exists()
        )
        resposta = cliente_de(self.participante).get(url("atividade-detail", self.atividade.pk))
        self.assertEqual(resposta.json()["vagas_restantes"], 2)

    def test_cancelar_inscricao_de_outra_pessoa_retorna_403(self):
        resposta = cliente_de(self.outro_participante).delete(url("inscricao-evento-detail", self.inscricao.pk))
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())

    def test_cancelar_inscricao_inexistente_retorna_404(self):
        cliente = cliente_de(self.participante)
        self.assertEqual(cliente.delete(url("inscricao-evento-detail", 999)).status_code, 404)
        self.assertEqual(cliente.delete(url("inscricao-evento-list") + "abc/").status_code, 404)


class InscricaoAtividadeTests(ApiComDadosDeCadastro):
    def inscrever(self, usuario, atividade):
        return cliente_de(usuario).post(url("inscricao-atividade-list"), {"atividade": atividade.pk}, format="json")

    def vagas(self, atividade):
        return APIClient().get(url("atividade-detail", atividade.pk)).json()["vagas_restantes"]

    def inscricao_da_atividade(self):
        return InscricaoAtividade.objects.get(atividade=self.atividade, inscricao_evento__participante=self.participante)

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
        inscrever(self.terceiro, self.evento)
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
        resposta = cliente_de(self.participante).post(url("inscricao-atividade-list"), {"atividade": 999}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("atividade", resposta.json())

    def test_cancelar_inscricao_na_atividade_devolve_a_vaga(self):
        self.assertEqual(self.vagas(self.atividade), 1)
        resposta = cliente_de(self.participante).delete(url("inscricao-atividade-detail", self.inscricao_da_atividade().pk))
        self.assertEqual(resposta.status_code, 204)
        self.assertEqual(self.vagas(self.atividade), 2)
        self.assertTrue(InscricaoEvento.objects.filter(participante=self.participante, evento=self.evento).exists())

    def test_cancelar_inscricao_de_outra_pessoa_retorna_403(self):
        inscricao = self.inscricao_da_atividade()
        resposta = cliente_de(self.outro_participante).delete(url("inscricao-atividade-detail", inscricao.pk))
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(InscricaoAtividade.objects.filter(pk=inscricao.pk).exists())

    def test_lista_traz_apenas_as_inscricoes_de_quem_pediu(self):
        resposta = cliente_de(self.outro_participante).get(url("inscricao-atividade-list"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["count"], 0)
        resposta = cliente_de(self.participante).get(url("inscricao-atividade-list"))
        self.assertEqual(resposta.json()["count"], 2)


class LeituraApiTests(ApiComDadosDeCadastro):
    def test_lista_eventos_publica(self):
        resposta = APIClient().get(url("evento-list"))
        self.assertEqual(resposta.status_code, 200)
        self.assertGreaterEqual(resposta.json()["count"], 1)

    def test_programacao_publica_retorna_atividades_e_dados_da_sala(self):
        resposta = APIClient().get(url("programacao-evento", self.evento.pk))
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["evento"]["id"], self.evento.pk)
        atividade = next(item for item in corpo["atividades"] if item["id"] == self.atividade.pk)
        self.assertEqual(atividade["sala_nome"], "Sala 101")
        self.assertIn("vagas_restantes", atividade)

    def test_agenda_exige_token(self):
        self.assertEqual(APIClient().get(url("agenda-participante")).status_code, 401)

    def test_agenda_retorna_apenas_atividades_do_participante_e_em_ordem(self):
        resposta = cliente_de(self.participante).get(url("agenda-participante"))
        self.assertEqual(resposta.status_code, 200)
        itens = resposta.json()
        self.assertTrue(itens)
        inicios = [item["inicio"] for item in itens]
        self.assertEqual(inicios, sorted(inicios))
        self.assertTrue(all(
            Atividade.objects.filter(
                pk=item["id"], inscricoes__inscricao_evento__participante=self.participante,
            ).exists()
            for item in itens
        ))
        ids_outro = {item["id"] for item in cliente_de(self.outro_participante).get(url("agenda-participante")).json()}
        self.assertNotIn(self.atividade.pk, ids_outro)
        self.assertIn(self.atividade.pk, {item["id"] for item in itens})

    def test_vagas_da_agenda_consideram_inscricoes_de_outros_participantes(self):
        InscricaoAtividade.objects.create(
            inscricao_evento=InscricaoEvento.objects.get(evento=self.evento, participante=self.outro_participante),
            atividade=self.atividade,
        )
        agenda = cliente_de(self.participante).get(url("agenda-participante")).json()
        vagas = {item["id"]: item["vagas_restantes"] for item in agenda}
        self.assertEqual(vagas[self.atividade.pk], 0)

    def test_lista_atividades_tem_paginacao_busca_e_ordenacao(self):
        cliente = APIClient()
        resposta = cliente.get(url("atividade-list"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("results", resposta.json())
        self.assertIn("count", resposta.json())

        busca = cliente.get(url("atividade-list"), {"search": "Django"})
        self.assertEqual(busca.status_code, 200)
        self.assertIn("Django na prática", [item["titulo"] for item in busca.json()["results"]])
        self.assertTrue(all(
            "django" in item["titulo"].lower() or "django" in item["descricao"].lower()
            for item in busca.json()["results"]
        ))

        ordenada = cliente.get(url("atividade-list"), {"ordering": "-inicio"})
        self.assertEqual(ordenada.status_code, 200)
        inicios = [item["inicio"] for item in ordenada.json()["results"]]
        self.assertEqual(inicios, sorted(inicios, reverse=True))

    def test_documentacao_openapi_e_disponivel(self):
        schema = APIClient().get(url("schema"), {"format": "json"})
        self.assertEqual(schema.status_code, 200)
        self.assertIn("openapi", schema.json())
        programacao = url("programacao-evento", 0).replace("/0/", "/{evento_id}/")
        self.assertIn(programacao, schema.json()["paths"])
        self.assertIn(url("agenda-participante"), schema.json()["paths"])
        self.assertEqual(APIClient().get(url("docs")).status_code, 200)


class BaseAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizador = criar_organizador("organizador_api")
        cls.outro_organizador = criar_organizador("outro_organizador_api")
        cls.participante_a = criar_participante("participante_api_a")
        cls.participante_b = criar_participante("participante_api_b")
        cls.participante_c = criar_participante("participante_api_c")
        cls.sala = criar_sala("Laboratório API", 2)
        cls.sala_alternativa = criar_sala("Sala Alternativa API", 3)
        cls.evento = criar_evento(
            cls.organizador, "Semana de Tecnologia API", data_inicio=date(2026, 11, 10), data_fim=date(2026, 11, 12)
        )
        cls.atividade = criar_atividade(cls.evento, cls.sala, "Introdução à API REST", data_hora(10, 9), data_hora(10, 10))

    def autenticar(self, usuario):
        self.client = cliente_de(usuario)

    def inscrever_no_evento(self, participante):
        return inscrever(participante, self.evento)

    def ocupar(self, inscricao, atividade):
        return InscricaoAtividade.objects.create(inscricao_evento=inscricao, atividade=atividade)

    def nova_atividade(self, titulo, inicio, fim):
        return criar_atividade(self.evento, self.sala_alternativa, titulo, inicio, fim)

    def inscrever_na_atividade(self, atividade):
        return self.client.post(url("inscricao-atividade-list"), {"atividade": atividade.pk}, format="json")

    def dados_atividade(self, titulo, sala, inicio, fim):
        return {
            "evento": self.evento.pk, "titulo": titulo, "tipo": Atividade.Tipo.PALESTRA, "descricao": "Descrição.",
            "responsavel": "Responsável", "sala": sala.pk, "inicio": inicio.isoformat(), "fim": fim.isoformat(),
        }

    def dados_evento(self, nome, **alteracoes):
        dados = {
            "nome": nome, "descricao": "Descrição.", "data_inicio": "2026-11-10",
            "data_fim": "2026-11-12", "inscricoes_abertas": True,
        }
        dados.update(alteracoes)
        return dados


class RegrasPelaApiTests(BaseAPITestCase):
    def test_regra1_api_aceita_quando_ha_vaga_na_sala(self):
        self.inscrever_no_evento(self.participante_a)
        self.autenticar(self.participante_a)
        resposta = self.inscrever_na_atividade(self.atividade)
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        self.assertTrue(InscricaoAtividade.objects.filter(
            inscricao_evento__participante=self.participante_a, atividade=self.atividade,
        ).exists())

    def test_regra1_api_recusa_quando_a_sala_esta_cheia(self):
        self.ocupar(self.inscrever_no_evento(self.participante_a), self.atividade)
        self.ocupar(self.inscrever_no_evento(self.participante_b), self.atividade)
        self.inscrever_no_evento(self.participante_c)
        self.autenticar(self.participante_c)
        resposta = self.inscrever_na_atividade(self.atividade)
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.atividade.inscricoes.count(), 2)
        self.assertFalse(self.atividade.inscricoes.filter(inscricao_evento__participante=self.participante_c).exists())

    def test_regra2_api_aceita_atividade_que_comeca_quando_a_outra_termina(self):
        seguinte = self.nova_atividade("Atividade sem conflito", data_hora(10, 10), data_hora(10, 11))
        self.ocupar(self.inscrever_no_evento(self.participante_a), self.atividade)
        self.autenticar(self.participante_a)
        resposta = self.inscrever_na_atividade(seguinte)
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        self.assertTrue(seguinte.inscricoes.filter(inscricao_evento__participante=self.participante_a).exists())

    def test_regra2_api_recusa_atividade_em_horario_sobreposto(self):
        conflitante = self.nova_atividade("Atividade com conflito", data_hora(10, 9, 30), data_hora(10, 10, 30))
        inscricao = self.inscrever_no_evento(self.participante_a)
        self.ocupar(inscricao, self.atividade)
        self.autenticar(self.participante_a)
        resposta = self.inscrever_na_atividade(conflitante)
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(InscricaoAtividade.objects.filter(inscricao_evento=inscricao).count(), 1)

    def test_regra3_api_aceita_mesma_sala_em_horario_livre(self):
        self.autenticar(self.organizador)
        resposta = self.client.post(url("atividade-list"), self.dados_atividade(
            "Atividade posterior", self.sala, data_hora(10, 10), data_hora(10, 11)
        ), format="json")
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        self.assertTrue(Atividade.objects.filter(titulo="Atividade posterior").exists())

    def test_regra3_api_recusa_mesma_sala_em_horario_sobreposto(self):
        self.autenticar(self.organizador)
        total = Atividade.objects.count()
        resposta = self.client.post(url("atividade-list"), self.dados_atividade(
            "Sala já ocupada", self.sala, data_hora(10, 9, 30), data_hora(10, 10, 30)
        ), format="json")
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Atividade.objects.count(), total)

    def test_regra4_api_aceita_quem_esta_inscrito_no_evento(self):
        self.inscrever_no_evento(self.participante_a)
        self.autenticar(self.participante_a)
        resposta = self.inscrever_na_atividade(self.atividade)
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        self.assertEqual(self.atividade.inscricoes.count(), 1)

    def test_regra4_api_recusa_quem_nao_esta_inscrito_no_evento(self):
        self.autenticar(self.participante_a)
        resposta = self.inscrever_na_atividade(self.atividade)
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resposta.json(), {"non_field_errors": ["Inscreva-se no evento antes de escolher uma atividade."]}
        )
        self.assertEqual(InscricaoAtividade.objects.count(), 0)

    def test_regra5_api_cancelar_no_evento_cancela_as_atividades(self):
        primeira = self.nova_atividade("Cancelamento A", data_hora(10, 11), data_hora(10, 12))
        segunda = self.nova_atividade("Cancelamento B", data_hora(10, 12), data_hora(10, 13))
        inscricao = self.inscrever_no_evento(self.participante_a)
        self.ocupar(inscricao, primeira)
        self.ocupar(inscricao, segunda)
        pk = inscricao.pk
        self.autenticar(self.participante_a)
        resposta = self.client.delete(url("inscricao-evento-detail", pk))
        self.assertEqual(resposta.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(InscricaoEvento.objects.filter(pk=pk).exists())
        self.assertFalse(InscricaoAtividade.objects.filter(atividade__in=[primeira, segunda]).exists())

    def test_regra5_api_recusa_cancelar_inscricao_alheia_e_preserva_as_atividades(self):
        inscricao = self.inscrever_no_evento(self.participante_a)
        self.ocupar(inscricao, self.atividade)
        self.autenticar(self.participante_b)
        resposta = self.client.delete(url("inscricao-evento-detail", inscricao.pk))
        self.assertEqual(resposta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(InscricaoEvento.objects.filter(pk=inscricao.pk).exists())
        self.assertEqual(inscricao.inscricoes_atividades.count(), 1)


class ValidacaoPelaApiTests(BaseAPITestCase):
    def setUp(self):
        self.autenticar(self.organizador)

    def test_api_recusa_evento_com_data_final_anterior_a_inicial(self):
        resposta = self.client.post(url("evento-list"), self.dados_evento(
            "Período inválido", data_inicio="2026-11-12", data_fim="2026-11-10"
        ), format="json")
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST, resposta.data)
        self.assertFalse(Evento.objects.filter(nome="Período inválido").exists())

    def test_api_recusa_atividade_com_fim_anterior_ao_inicio(self):
        resposta = self.client.post(url("atividade-list"), self.dados_atividade(
            "Intervalo inválido", self.sala_alternativa, data_hora(10, 10), data_hora(10, 9)
        ), format="json")
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST, resposta.data)
        self.assertFalse(Atividade.objects.filter(titulo="Intervalo inválido").exists())

    def test_api_recusa_atividade_fora_do_periodo_do_evento(self):
        resposta = self.client.post(url("atividade-list"), self.dados_atividade(
            "Fora do período", self.sala_alternativa, data_hora(13, 9), data_hora(13, 10)
        ), format="json")
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST, resposta.data)
        self.assertFalse(Atividade.objects.filter(titulo="Fora do período").exists())


class PortaAbertaDaApiTests(BaseAPITestCase):
    def test_lista_de_eventos_e_publica_e_retorna_dados_esperados(self):
        resposta = self.client.get(url("evento-list"))
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        evento = next(item for item in resposta.data["results"] if item["id"] == self.evento.pk)
        self.assertEqual(evento["nome"], self.evento.nome)
        self.assertEqual(set(evento.keys()), CAMPOS_EVENTO)
        self.assertEqual(evento["organizador"], self.organizador.username)
        self.assertNotIn("organizador_id", evento)
        self.assertNotIn("email", evento)
        self.assertNotIn("participante", evento)

    def test_programacao_publica_retorna_dados_esperados_e_nada_privado(self):
        resposta = self.client.get(url("programacao-evento", self.evento.pk))
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(set(resposta.data.keys()), {"evento", "atividades"})

        evento = resposta.data["evento"]
        self.assertEqual(evento["nome"], self.evento.nome)
        self.assertEqual(set(evento.keys()), CAMPOS_EVENTO)
        self.assertEqual(evento["organizador"], self.organizador.username)
        self.assertNotIn("organizador_id", evento)
        self.assertNotIn("email", evento)
        self.assertNotIn("participante", evento)

        self.assertEqual(len(resposta.data["atividades"]), 1)
        atividade = resposta.data["atividades"][0]
        self.assertEqual(atividade["titulo"], self.atividade.titulo)
        self.assertEqual(atividade["sala_nome"], self.sala.nome)
        self.assertEqual(set(atividade.keys()), CAMPOS_ATIVIDADE)
        self.assertNotIn("email", atividade)
        self.assertNotIn("participante", atividade)
        self.assertNotIn("inscricoes", atividade)

    def test_lista_de_atividades_e_publica_e_retorna_so_os_campos_esperados(self):
        resposta = self.client.get(url("atividade-list"))
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        atividade = next(item for item in resposta.data["results"] if item["id"] == self.atividade.pk)
        self.assertEqual(atividade["sala_nome"], self.sala.nome)
        self.assertEqual(set(atividade.keys()), CAMPOS_ATIVIDADE)
        self.assertNotIn("email", atividade)
        self.assertNotIn("participante", atividade)
        self.assertNotIn("inscricoes", atividade)

    def test_consulta_de_salas_e_publica_e_retorna_so_os_campos_esperados(self):
        resposta = self.client.get(url("sala-list"))
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        sala = next(item for item in resposta.data["results"] if item["nome"] == self.sala.nome)
        self.assertEqual(set(sala.keys()), CAMPOS_SALA)
        self.assertEqual(sala["capacidade"], 2)

    def test_programacao_publica_nao_revela_quem_esta_inscrito(self):
        self.ocupar(self.inscrever_no_evento(self.participante_a), self.atividade)
        resposta = self.client.get(url("programacao-evento", self.evento.pk))
        self.assertNotContains(resposta, self.participante_a.username)
        self.assertEqual(resposta.data["atividades"][0]["vagas_restantes"], 1)


class PortaFechadaDaApiTests(BaseAPITestCase):
    def test_endpoint_protegido_sem_token_responde_401(self):
        resposta = self.client.post(url("evento-list"), self.dados_evento("Evento sem token"), format="json")
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Evento.objects.filter(nome="Evento sem token").exists())

    def test_agenda_sem_token_retorna_401(self):
        resposta = self.client.get(url("agenda-participante"))
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_invalido_retorna_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token token-invalido")
        resposta = self.client.get(url("agenda-participante"))
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_usuario_autenticado_sem_permissao_nao_cria_evento(self):
        self.autenticar(self.participante_a)
        resposta = self.client.post(url("evento-list"), self.dados_evento("Evento de participante"), format="json")
        self.assertEqual(resposta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Evento.objects.filter(nome="Evento de participante").exists())

    def test_participante_nao_pode_criar_atividade(self):
        self.autenticar(self.participante_a)
        total = Atividade.objects.count()
        resposta = self.client.post(url("atividade-list"), self.dados_atividade(
            "Atividade de participante", self.sala_alternativa, data_hora(10, 11), data_hora(10, 12)
        ), format="json")
        self.assertEqual(resposta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Atividade.objects.count(), total)

    def test_token_do_organizador_permite_criar_evento(self):
        self.autenticar(self.organizador)
        resposta = self.client.post(url("evento-list"), self.dados_evento("Evento criado pela API"), format="json")
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        self.assertTrue(Evento.objects.filter(nome="Evento criado pela API", organizador=self.organizador).exists())

    def test_participante_autenticado_pode_se_inscrever_no_evento(self):
        self.autenticar(self.participante_a)
        resposta = self.client.post(url("inscricao-evento-list"), {"evento": self.evento.pk}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED, resposta.data)
        self.assertTrue(InscricaoEvento.objects.filter(evento=self.evento, participante=self.participante_a).exists())

    def test_organizador_nao_edita_evento_de_outro(self):
        nome_original = self.evento.nome
        self.autenticar(self.outro_organizador)
        resposta = self.client.patch(url("evento-detail", self.evento.pk), {"nome": "Alterado"}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_403_FORBIDDEN)
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.nome, nome_original)

    def test_usuario_nao_cancela_inscricao_de_outra_pessoa(self):
        inscricao = self.inscrever_no_evento(self.participante_a)
        self.autenticar(self.participante_b)
        resposta = self.client.delete(url("inscricao-evento-detail", inscricao.pk))
        self.assertEqual(resposta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(InscricaoEvento.objects.filter(pk=inscricao.pk).exists())


class ConsultasDaApiTests(BaseAPITestCase):
    def test_programacao_publica_usa_numero_fixo_de_consultas(self):
        endereco = url("programacao-evento", self.evento.pk)
        with self.assertNumQueries(2):
            pequena = self.client.get(endereco)
        self.assertEqual(pequena.status_code, status.HTTP_200_OK)
        self.assertEqual(len(pequena.data["atividades"]), 1)

        for indice in range(10):
            inicio = data_hora(10, 11 + indice)
            self.nova_atividade(f"Atividade adicional {indice + 1}", inicio, inicio + timedelta(minutes=30))

        with self.assertNumQueries(2):
            grande = self.client.get(endereco)
        self.assertEqual(grande.status_code, status.HTTP_200_OK)
        self.assertEqual(len(grande.data["atividades"]), 11)
