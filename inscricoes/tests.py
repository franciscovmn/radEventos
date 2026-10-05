from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala


class EventosTestCase(TestCase):
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
        cls.posterior = Atividade.objects.get(titulo="Comunicação científica")
        cls.inscricao = InscricaoEvento.objects.get(evento=cls.evento, participante=cls.participante)

    def entrar(self, usuario):
        self.client.force_login(usuario)

    def url(self, nome, objeto):
        return reverse(f"eventos:{nome}", args=[objeto.pk])

    def dados_atividade(self, **alteracoes):
        dados = {
            "titulo": "Nova palestra", "tipo": "PA", "descricao": "Uma palestra.",
            "responsavel": "Maria", "sala": Sala.objects.get(nome="Auditório").pk,
            "inicio": "2026-10-21T08:00", "fim": "2026-10-21T09:00",
        }
        dados.update(alteracoes)
        return dados

    def test_programacao_publica_e_vagas(self):
        self.assertEqual(self.client.get(reverse("eventos:lista")).status_code, 200)
        resposta = self.client.get(self.url("detalhe", self.evento))
        self.assertContains(resposta, "Django na prática")
        self.assertContains(resposta, "Ana Souza")
        self.assertContains(resposta, "1 de 2 vagas disponíveis")
        self.assertNotContains(resposta, self.url("inscrever_atividade", self.atividade))
        self.assertEqual(
            [atividade.pk for atividade in resposta.context["atividades"]],
            [self.atividade.pk, self.conflito_interno.pk, self.seguinte.pk],
        )

    def test_anonimo_precisa_de_login(self):
        for url in [
            self.url("inscrever_evento", self.evento), self.url("inscrever_atividade", self.atividade),
            reverse("eventos:agenda"), reverse("eventos:novo"),
        ]:
            resposta = self.client.post(url)
            self.assertEqual(resposta.status_code, 302)
            self.assertTrue(resposta.url.startswith(reverse("login")))

    def test_cadastro_login_logout_sem_permissoes(self):
        resposta = self.client.post(reverse("cadastro"), {
            "username": "novato", "password1": "Cadastro@2026", "password2": "Cadastro@2026",
            "is_staff": "on", "organizador": self.organizador.pk,
        })
        self.assertRedirects(resposta, reverse("login"))
        usuario = User.objects.get(username="novato")
        self.assertTrue(usuario.check_password("Cadastro@2026"))
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.has_perm("inscricoes.organizar_eventos"))
        self.assertEqual(usuario.groups.count(), 0)
        self.assertRedirects(self.client.post(reverse("login"), {
            "username": "novato", "password": "Cadastro@2026"
        }), reverse("eventos:lista"))
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("eventos:lista"))

    def test_criacao_evento_atribui_organizador_no_servidor(self):
        self.entrar(self.organizador)
        resposta = self.client.get(reverse("eventos:novo"))
        self.assertNotContains(resposta, 'name="organizador"')
        resposta = self.client.post(reverse("eventos:novo"), {
            "nome": "Novo evento", "descricao": "Descrição do novo evento",
            "data_inicio": "2026-11-01", "data_fim": "2026-11-02",
            "inscricoes_abertas": "on", "organizador": self.outro_organizador.pk,
        })
        novo = Evento.objects.get(nome="Novo evento")
        self.assertRedirects(resposta, novo.get_absolute_url())
        self.assertEqual(novo.organizador, self.organizador)

    def test_participante_nao_gerencia_eventos(self):
        self.entrar(self.participante)
        for url in [reverse("eventos:novo"), self.url("editar", self.evento),
                    self.url("excluir", self.evento), self.url("painel", self.evento),
                    self.url("nova_atividade", self.evento), self.url("editar_atividade", self.atividade)]:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_propriedade_em_todas_as_rotas_de_organizador(self):
        self.entrar(self.outro_organizador)
        for nome, objeto in [
            ("editar", self.evento), ("excluir", self.evento), ("painel", self.evento),
            ("nova_atividade", self.evento), ("editar_atividade", self.atividade),
            ("excluir_atividade", self.atividade),
        ]:
            self.assertEqual(self.client.get(self.url(nome, objeto)).status_code, 403)
            if nome != "painel":
                self.assertEqual(self.client.post(self.url(nome, objeto), {}).status_code, 403)
        resposta = self.client.get(self.url("detalhe", self.evento))
        self.assertNotContains(resposta, self.url("editar", self.evento))
        self.assertNotContains(resposta, self.url("painel", self.evento))

    def test_atividade_fora_do_periodo_ou_intervalo_invalido(self):
        self.entrar(self.organizador)
        for inicio, fim in [
            ("2026-10-18T10:00", "2026-10-18T11:00"),
            ("2026-10-21T23:30", "2026-10-22T00:30"),
            ("2026-10-21T09:00", "2026-10-21T08:00"),
            ("2026-10-21T09:00", "2026-10-21T09:00"),
        ]:
            resposta = self.client.post(self.url("nova_atividade", self.evento), self.dados_atividade(
                inicio=inicio, fim=fim
            ))
            self.assertEqual(resposta.status_code, 200)
            self.assertTrue(resposta.context["form"].errors)
        self.assertFalse(Atividade.objects.filter(titulo="Nova palestra").exists())

    def test_sobreposicoes_de_sala_entre_eventos(self):
        self.entrar(self.outro_organizador)
        for inicio, fim in [
            ("08:30", "09:30"), ("09:30", "10:30"),
            ("08:30", "11:30"), ("09:15", "09:45"), ("09:00", "10:00"),
        ]:
            resposta = self.client.post(self.url("nova_atividade", self.outro_evento), self.dados_atividade(
                sala=self.atividade.sala_id,
                inicio=f"2026-10-19T{inicio}", fim=f"2026-10-19T{fim}",
            ))
            self.assertContains(resposta, "A sala já está ocupada nesse horário.")
        self.assertFalse(Atividade.objects.filter(titulo="Nova palestra").exists())

    def test_atividade_adjacente_na_mesma_sala_e_edicao_propria(self):
        self.entrar(self.organizador)
        resposta = self.client.post(self.url("nova_atividade", self.evento), self.dados_atividade(
            sala=self.atividade.sala_id, inicio="2026-10-19T11:00", fim="2026-10-19T12:00"
        ))
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        nova = Atividade.objects.get(titulo="Nova palestra")
        resposta = self.client.post(self.url("editar_atividade", nova), self.dados_atividade(
            sala=nova.sala_id, inicio="2026-10-19T11:00", fim="2026-10-19T12:00"
        ))
        self.assertRedirects(resposta, self.evento.get_absolute_url())

    def test_sala_ocupada_tambem_impede_edicao(self):
        self.entrar(self.organizador)
        resposta = self.client.post(self.url("editar_atividade", self.seguinte), self.dados_atividade(
            sala=self.atividade.sala_id, inicio="2026-10-19T09:00", fim="2026-10-19T10:00"
        ))
        self.assertContains(resposta, "A sala já está ocupada nesse horário.")
        self.seguinte.refresh_from_db()
        self.assertEqual(timezone.localtime(self.seguinte.inicio).hour, 10)

    def test_inscricao_evento_duplicada_e_fechada(self):
        self.entrar(self.terceiro)
        self.assertRedirects(self.client.post(self.url("inscrever_evento", self.evento)), self.evento.get_absolute_url())
        self.client.post(self.url("inscrever_evento", self.evento))
        self.assertEqual(InscricaoEvento.objects.filter(evento=self.evento, participante=self.terceiro).count(), 1)
        resposta = self.client.post(self.url("inscrever_evento", self.fechado), follow=True)
        self.assertContains(resposta, "As inscrições deste evento estão fechadas.")
        self.assertFalse(InscricaoEvento.objects.filter(evento=self.fechado, participante=self.terceiro).exists())

    def test_sem_inscricao_no_evento_nao_escolhe_atividade(self):
        self.entrar(self.terceiro)
        resposta = self.client.get(self.url("detalhe", self.evento))
        self.assertNotContains(resposta, self.url("inscrever_atividade", self.atividade))
        resposta = self.client.post(self.url("inscrever_atividade", self.atividade), follow=True)
        self.assertContains(resposta, "Inscreva-se no evento antes de escolher uma atividade.")
        self.assertFalse(InscricaoAtividade.objects.filter(inscricao_evento__participante=self.terceiro).exists())

    def test_limite_de_vagas_e_interface_lotada(self):
        self.entrar(self.outro_participante)
        self.client.post(self.url("inscrever_atividade", self.atividade))
        self.assertEqual(self.atividade.inscricoes.count(), 2)
        self.client.post(self.url("inscrever_atividade", self.atividade))
        self.assertEqual(self.atividade.inscricoes.count(), 2)
        self.entrar(self.terceiro)
        self.client.post(self.url("inscrever_evento", self.evento))
        resposta = self.client.post(self.url("inscrever_atividade", self.atividade), follow=True)
        self.assertContains(resposta, "Esta atividade está lotada.")
        self.assertContains(resposta, "0 de 2 vagas disponíveis")
        self.assertNotContains(resposta, self.url("inscrever_atividade", self.atividade))
        self.assertEqual(self.atividade.inscricoes.count(), 2)

    def test_conflitos_da_agenda_dentro_e_fora_do_evento(self):
        self.entrar(self.participante)
        for atividade in [self.conflito_interno, self.conflito_externo]:
            resposta = self.client.get(self.url("detalhe", atividade.evento))
            self.assertNotContains(resposta, self.url("inscrever_atividade", atividade))
            resposta = self.client.post(self.url("inscrever_atividade", atividade), follow=True)
            self.assertContains(resposta, "Esta atividade conflita com outra inscrição na sua agenda.")
            self.assertFalse(atividade.inscricoes.exists())

    def test_atividade_adjacente_nao_conflita_com_agenda(self):
        self.entrar(self.participante)
        self.client.post(self.url("inscrever_atividade", self.seguinte))
        self.assertTrue(self.seguinte.inscricoes.filter(inscricao_evento=self.inscricao).exists())

    def test_cancelar_atividade_libera_vaga_e_preserva_evento(self):
        self.entrar(self.participante)
        inscricao = self.atividade.inscricoes.get(inscricao_evento=self.inscricao)
        self.client.post(self.url("cancelar_atividade", inscricao))
        self.assertTrue(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())
        self.assertFalse(InscricaoAtividade.objects.filter(pk=inscricao.pk).exists())
        self.assertContains(self.client.get(self.url("detalhe", self.evento)), "2 de 2 vagas disponíveis")

    def test_cancelar_evento_remove_suas_atividades(self):
        self.entrar(self.participante)
        self.client.post(self.url("inscrever_atividade", self.seguinte))
        self.client.post(self.url("cancelar_evento", self.inscricao))
        self.assertFalse(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())
        self.assertFalse(InscricaoAtividade.objects.filter(inscricao_evento_id=self.inscricao.pk).exists())
        self.assertTrue(self.posterior.inscricoes.filter(inscricao_evento__participante=self.participante).exists())

    def test_nao_cancela_inscricao_alheia(self):
        self.entrar(self.outro_participante)
        inscricao = self.atividade.inscricoes.get(inscricao_evento=self.inscricao)
        for nome, objeto in [("cancelar_evento", self.inscricao), ("cancelar_atividade", inscricao)]:
            self.assertEqual(self.client.post(self.url(nome, objeto)).status_code, 403)
        self.assertTrue(InscricaoAtividade.objects.filter(pk=inscricao.pk).exists())

    def test_agenda_isolada_ordenada_com_eventos_diferentes(self):
        self.entrar(self.participante)
        resposta = self.client.get(reverse("eventos:agenda"))
        inscricoes = list(resposta.context["inscricoes"])
        self.assertEqual([item.atividade_id for item in inscricoes], [self.atividade.pk, self.posterior.pk])
        self.assertContains(resposta, self.evento.nome)
        self.assertContains(resposta, self.outro_evento.nome)
        self.entrar(self.outro_participante)
        self.assertNotContains(self.client.get(reverse("eventos:agenda")), self.atividade.titulo)

    def test_painel_inscritos_contagem_e_vagas(self):
        self.entrar(self.organizador)
        resposta = self.client.get(self.url("painel", self.evento))
        self.assertContains(resposta, "participante4")
        self.assertContains(resposta, "1 inscritos")
        self.assertContains(resposta, "1 vagas restantes")
        self.assertNotContains(resposta, "Comunicação científica")
        self.assertEqual(self.client.get(self.url("painel", self.outro_evento)).status_code, 403)

    def test_mutacoes_exigem_post_e_csrf(self):
        self.entrar(self.participante)
        inscricao = self.atividade.inscricoes.get(inscricao_evento=self.inscricao)
        urls = [
            self.url("inscrever_evento", self.outro_evento), self.url("inscrever_atividade", self.seguinte),
            self.url("cancelar_evento", self.inscricao), self.url("cancelar_atividade", inscricao),
        ]
        cliente_csrf = Client(enforce_csrf_checks=True)
        cliente_csrf.force_login(self.participante)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(cliente_csrf.post(url).status_code, 403)
        self.assertTrue(InscricaoAtividade.objects.filter(pk=inscricao.pk).exists())

    def test_exclusao_so_no_post(self):
        self.entrar(self.organizador)
        self.assertEqual(self.client.get(self.url("excluir_atividade", self.seguinte)).status_code, 200)
        self.assertTrue(Atividade.objects.filter(pk=self.seguinte.pk).exists())
        self.assertRedirects(self.client.post(self.url("excluir_atividade", self.seguinte)), self.evento.get_absolute_url())
        self.assertFalse(Atividade.objects.filter(pk=self.seguinte.pk).exists())
        self.assertEqual(self.client.get(self.url("excluir", self.evento)).status_code, 200)
        self.assertTrue(Evento.objects.filter(pk=self.evento.pk).exists())
        self.assertRedirects(self.client.post(self.url("excluir", self.evento)), reverse("eventos:lista"))
        self.assertFalse(Atividade.objects.filter(evento_id=self.evento.pk).exists())
        self.assertFalse(InscricaoEvento.objects.filter(evento_id=self.evento.pk).exists())

    def test_vinculo_da_inscricao_tem_que_ser_do_mesmo_evento(self):
        with self.assertRaisesMessage(ValidationError, "A inscrição precisa ser do mesmo evento da atividade."):
            InscricaoAtividade.objects.create(inscricao_evento=self.inscricao, atividade=self.conflito_externo)

    def test_edicao_nao_invalida_periodo_capacidade_ou_agenda(self):
        self.evento.data_inicio += timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.evento.save()
        self.atividade.sala.capacidade = 0
        with self.assertRaises(ValidationError):
            self.atividade.sala.save()
        self.posterior.inicio = self.atividade.inicio
        self.posterior.fim = self.atividade.fim
        self.posterior.sala = Sala.objects.create(nome="Sala de teste", bloco="D", capacidade=10)
        with self.assertRaisesMessage(ValidationError, "O novo horário conflita com a agenda de um participante inscrito."):
            self.posterior.save()

    def test_admin_entidades_registradas_e_dados_excluidos_dos_forms(self):
        self.entrar(User.objects.get(username="admin"))
        for model in ["sala", "evento", "atividade", "inscricaoevento", "inscricaoatividade"]:
            self.assertEqual(self.client.get(reverse(f"admin:inscricoes_{model}_changelist")).status_code, 200)
        resposta = self.client.get(reverse("admin:inscricoes_evento_add"))
        self.assertNotContains(resposta, 'name="organizador"')
        resposta = self.client.get(reverse("admin:inscricoes_inscricaoevento_add"))
        self.assertNotContains(resposta, 'name="participante"')

    def test_dados_de_teste_podem_ser_cadastrados_novamente(self):
        call_command("cadastrar_dados", verbosity=0)
        self.assertEqual(Evento.objects.count(), 3)
        self.assertEqual(Atividade.objects.count(), 5)
        self.assertEqual(Sala.objects.count(), 3)


class ConcorrenciaTestCase(TransactionTestCase):
    def setUp(self):
        call_command("cadastrar_dados", verbosity=0)

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
