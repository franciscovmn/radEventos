from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth.models import User
from django.db import close_old_connections
from django.test import Client, TransactionTestCase
from django.urls import reverse

from inscricoes.models import Atividade, InscricaoAtividade, InscricaoEvento, Sala

from .base import cadastrar_dados, cliente_de


class ConcorrenciaNoSiteTests(TransactionTestCase):
    def setUp(self):
        cadastrar_dados()

    def enviar_juntos(self, envios):
        barreira = Barrier(len(envios))
        clientes = []
        for usuario, url, dados in envios:
            cliente = Client()
            cliente.force_login(usuario)
            clientes.append((cliente, url, dados))

        def enviar(envio):
            close_old_connections()
            try:
                cliente, url, dados = envio
                barreira.wait(timeout=10)
                return cliente.post(url, dados).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(envios)) as executor:
            return list(executor.map(enviar, clientes))

    def test_dois_envios_nao_ocupam_a_mesma_ultima_vaga(self):
        atividade = Atividade.objects.get(titulo="Django na prática")
        quinto = User.objects.get(username="participante5")
        sexto = User.objects.create_user(username="participante6", password="Eventos@2026")
        InscricaoEvento.objects.create(evento=atividade.evento, participante=sexto)
        url = reverse("eventos:inscrever_atividade", args=[atividade.pk])
        self.assertEqual(self.enviar_juntos([(quinto, url, {}), (sexto, url, {})]), [302, 302])
        self.assertEqual(atividade.inscricoes.count(), 2)

    def test_envios_simultaneos_respeitam_agenda_entre_eventos(self):
        usuario = User.objects.create_user(username="participante6", password="Eventos@2026")
        atividades = [Atividade.objects.get(titulo=titulo) for titulo in ["Django na prática", "Pesquisa e inovação"]]
        for atividade in atividades:
            InscricaoEvento.objects.create(evento=atividade.evento, participante=usuario)
        envios = [(usuario, reverse("eventos:inscrever_atividade", args=[atividade.pk]), {}) for atividade in atividades]
        self.assertEqual(self.enviar_juntos(envios), [302, 302])
        self.assertEqual(InscricaoAtividade.objects.filter(inscricao_evento__participante=usuario).count(), 1)

    def test_cadastros_simultaneos_respeitam_ocupacao_da_sala(self):
        sala = Sala.objects.get(nome="Laboratório de Informática")
        envios = []
        for nome in ["organizador2", "organizador3"]:
            usuario = User.objects.get(username=nome)
            evento = usuario.eventos_organizados.filter(inscricoes_abertas=True).get()
            envios.append((usuario, reverse("eventos:nova_atividade", args=[evento.pk]), {
                "titulo": f"Atividade de {nome}", "tipo": "PA", "descricao": "Descrição",
                "responsavel": "Maria", "sala": sala.pk,
                "inicio": "2026-10-20T10:00", "fim": "2026-10-20T11:00",
            }))
        self.assertEqual(sorted(self.enviar_juntos(envios)), [200, 302])
        self.assertEqual(Atividade.objects.filter(sala=sala, inicio__date="2026-10-20").count(), 1)


class ConcorrenciaNaApiTests(TransactionTestCase):
    def setUp(self):
        cadastrar_dados()
        self.url = reverse("api:inscricao-atividade-list")

    def enviar_juntos(self, envios):
        barreira = Barrier(len(envios))

        def enviar(envio):
            close_old_connections()
            try:
                usuario, dados = envio
                cliente = cliente_de(usuario)
                barreira.wait(timeout=10)
                return cliente.post(self.url, dados, format="json").status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(envios)) as executor:
            return list(executor.map(enviar, envios))

    def test_dois_envios_nao_ocupam_a_mesma_ultima_vaga(self):
        atividade = Atividade.objects.get(titulo="Django na prática")
        quinto = User.objects.get(username="participante5")
        sexto = User.objects.create_user(username="participante6", password="Eventos@2026")
        InscricaoEvento.objects.create(evento=atividade.evento, participante=sexto)
        envios = [(usuario, {"atividade": atividade.pk}) for usuario in (quinto, sexto)]
        self.assertEqual(sorted(self.enviar_juntos(envios)), [201, 400])
        self.assertEqual(atividade.inscricoes.count(), 2)

    def test_envios_simultaneos_respeitam_agenda_entre_eventos(self):
        usuario = User.objects.create_user(username="participante6", password="Eventos@2026")
        atividades = [Atividade.objects.get(titulo=titulo) for titulo in ["Django na prática", "Pesquisa e inovação"]]
        for atividade in atividades:
            InscricaoEvento.objects.create(evento=atividade.evento, participante=usuario)
        envios = [(usuario, {"atividade": atividade.pk}) for atividade in atividades]
        self.assertEqual(sorted(self.enviar_juntos(envios)), [201, 400])
        self.assertEqual(InscricaoAtividade.objects.filter(inscricao_evento__participante=usuario).count(), 1)
