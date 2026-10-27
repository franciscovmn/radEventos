from django.core.management import call_command
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from inscricoes.models import Atividade, Evento, InscricaoAtividade, InscricaoEvento


class LeituraApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cadastrar_dados", verbosity=0)
        cls.participante = User.objects.get(username="participante4")
        cls.outro_participante = User.objects.get(username="participante5")
        cls.evento = Evento.objects.get(nome="Semana de Tecnologia")
        cls.atividade = Atividade.objects.get(titulo="Django na prática")

    def cliente_com_token(self, usuario):
        cliente = APIClient()
        token, _ = Token.objects.get_or_create(user=usuario)
        cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return cliente

    def test_lista_eventos_publica(self):
        resposta = APIClient().get("/api/eventos/")
        self.assertEqual(resposta.status_code, 200)
        self.assertGreaterEqual(resposta.json()["count"], 1)

    def test_programacao_publica_retorna_atividades_e_dados_da_sala(self):
        resposta = APIClient().get(f"/api/eventos/{self.evento.pk}/programacao/")
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["evento"]["id"], self.evento.pk)
        atividade = next(item for item in corpo["atividades"] if item["id"] == self.atividade.pk)
        self.assertEqual(atividade["sala_nome"], "Sala 101")
        self.assertIn("vagas_restantes", atividade)

    def test_agenda_exige_token(self):
        self.assertEqual(APIClient().get("/api/agenda/").status_code, 401)

    def test_agenda_retorna_apenas_atividades_do_participante_e_em_ordem(self):
        resposta = self.cliente_com_token(self.participante).get("/api/agenda/")
        self.assertEqual(resposta.status_code, 200)
        itens = resposta.json()
        self.assertTrue(itens)
        inicios = [item["inicio"] for item in itens]
        self.assertEqual(inicios, sorted(inicios))
        self.assertTrue(all(
            Atividade.objects.filter(
                pk=item["id"],
                inscricoes__inscricao_evento__participante=self.participante,
            ).exists()
            for item in itens
        ))

        resposta_outro = self.cliente_com_token(self.outro_participante).get("/api/agenda/")
        ids_outro = {item["id"] for item in resposta_outro.json()}
        ids_participante = {item["id"] for item in itens}
        self.assertNotIn(self.atividade.pk, ids_outro)
        self.assertIn(self.atividade.pk, ids_participante)

    def test_vagas_da_agenda_consideram_inscricoes_de_outros_participantes(self):
        InscricaoAtividade.objects.create(
            inscricao_evento=InscricaoEvento.objects.get(evento=self.evento, participante=self.outro_participante),
            atividade=self.atividade,
        )
        agenda = self.cliente_com_token(self.participante).get("/api/agenda/").json()
        vagas = {item["id"]: item["vagas_restantes"] for item in agenda}
        self.assertEqual(vagas[self.atividade.pk], 0)

    def test_lista_atividades_tem_paginacao_busca_e_ordenacao(self):
        cliente = APIClient()
        resposta = cliente.get("/api/atividades/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("results", resposta.json())
        self.assertIn("count", resposta.json())

        busca = cliente.get("/api/atividades/?search=Django")
        self.assertEqual(busca.status_code, 200)
        titulos = [item["titulo"] for item in busca.json()["results"]]
        self.assertIn("Django na prática", titulos)
        self.assertTrue(all("django" in item["titulo"].lower() or "django" in item["descricao"].lower()
                            for item in busca.json()["results"]))

        ordenada = cliente.get("/api/atividades/?ordering=-inicio")
        self.assertEqual(ordenada.status_code, 200)
        inicios = [item["inicio"] for item in ordenada.json()["results"]]
        self.assertEqual(inicios, sorted(inicios, reverse=True))

    def test_documentacao_openapi_e_disponivel(self):
        schema = APIClient().get("/api/schema/?format=json")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("openapi", schema.json())

        self.assertIn("/api/eventos/{evento_id}/programacao/", schema.json()["paths"])
        self.assertIn("/api/agenda/", schema.json()["paths"])

        docs = APIClient().get("/api/docs/")
        self.assertEqual(docs.status_code, 200)
