from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from inscricoes.models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala

from .base import (
    CenarioRegras, DadosDeCadastro, cadastrar_dados, criar_atividade, criar_sala, horario, mensagens, ocupar,
)


def url(nome, objeto):
    return reverse(f"eventos:{nome}", args=[objeto.pk])


class RegrasPeloSiteTests(CenarioRegras):
    def inscrever_em(self, atividade, usuario=None):
        self.client.force_login(usuario or self.participante)
        return self.client.post(url("inscrever_atividade", atividade), follow=True)

    def criar_atividade_pelo_site(self, inicio, fim):
        self.client.force_login(self.organizador)
        return self.client.post(reverse("eventos:nova_atividade", args=[self.evento.pk]), {
            "titulo": "Nova atividade", "tipo": "PA", "descricao": "Nova.", "responsavel": "Joana",
            "sala": self.sala.pk, "inicio": inicio, "fim": fim,
        })

    def test_regra1_site_aceita_quando_ha_vaga_na_sala(self):
        resposta = self.inscrever_em(self.atividade)
        self.assertIn("Inscrição na atividade confirmada.", mensagens(resposta))
        self.assertTrue(self.atividade.inscricoes.filter(inscricao_evento=self.inscricao).exists())

    def test_regra1_site_recusa_quando_a_sala_esta_cheia(self):
        ocupar(self.inscricao_colega, self.atividade)
        resposta = self.inscrever_em(self.atividade)
        self.assertIn("Esta atividade está lotada.", mensagens(resposta))
        self.assertEqual(self.atividade.inscricoes.count(), 1)
        self.assertFalse(self.atividade.inscricoes.filter(inscricao_evento=self.inscricao).exists())

    def test_regra2_site_aceita_atividade_que_comeca_quando_a_outra_termina(self):
        ocupar(self.inscricao, self.simultanea)
        resposta = self.inscrever_em(self.seguinte)
        self.assertIn("Inscrição na atividade confirmada.", mensagens(resposta))
        self.assertTrue(self.seguinte.inscricoes.filter(inscricao_evento=self.inscricao).exists())

    def test_regra2_site_recusa_atividade_em_horario_sobreposto(self):
        ocupar(self.inscricao, self.atividade)
        resposta = self.inscrever_em(self.simultanea)
        self.assertIn("Esta atividade conflita com outra inscrição na sua agenda.", mensagens(resposta))
        self.assertFalse(self.simultanea.inscricoes.exists())

    def test_regra3_site_aceita_mesma_sala_em_horario_livre(self):
        resposta = self.criar_atividade_pelo_site("2030-03-04T10:00", "2030-03-04T11:00")
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        self.assertTrue(Atividade.objects.filter(titulo="Nova atividade", sala=self.sala).exists())

    def test_regra3_site_recusa_mesma_sala_em_horario_sobreposto(self):
        resposta = self.criar_atividade_pelo_site("2030-03-04T09:30", "2030-03-04T10:30")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["form"].errors, {"sala": ["A sala já está ocupada nesse horário."]})
        self.assertFalse(Atividade.objects.filter(titulo="Nova atividade").exists())

    def test_regra4_site_aceita_quem_esta_inscrito_no_evento(self):
        resposta = self.inscrever_em(self.seguinte)
        self.assertIn("Inscrição na atividade confirmada.", mensagens(resposta))
        self.assertEqual(self.seguinte.inscricoes.count(), 1)

    def test_regra4_site_recusa_quem_nao_esta_inscrito_no_evento(self):
        resposta = self.inscrever_em(self.seguinte, self.sem_inscricao)
        self.assertIn("Inscreva-se no evento antes de escolher uma atividade.", mensagens(resposta))
        self.assertFalse(self.seguinte.inscricoes.exists())

    def test_regra5_site_cancelar_no_evento_cancela_as_atividades(self):
        ocupar(self.inscricao, self.atividade)
        ocupar(self.inscricao, self.seguinte)
        pk = self.inscricao.pk
        self.client.force_login(self.participante)
        self.client.post(url("cancelar_evento", self.inscricao))
        self.assertFalse(InscricaoEvento.objects.filter(pk=pk).exists())
        self.assertFalse(InscricaoAtividade.objects.filter(inscricao_evento_id=pk).exists())

    def test_regra5_site_recusa_cancelar_inscricao_alheia_e_preserva_as_atividades(self):
        ocupar(self.inscricao, self.atividade)
        self.client.force_login(self.colega)
        resposta = self.client.post(url("cancelar_evento", self.inscricao))
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())
        self.assertEqual(self.inscricao.inscricoes_atividades.count(), 1)


class ProgramacaoDoSiteTests(CenarioRegras):
    def setUp(self):
        self.resposta = self.client.get(url("detalhe", self.evento))

    def test_programacao_responde_200(self):
        self.assertEqual(self.resposta.status_code, 200)

    def test_programacao_usa_o_template_de_detalhe(self):
        self.assertTemplateUsed(self.resposta, "eventos/detalhe.html")

    def test_programacao_mostra_titulo_sala_e_vagas_das_atividades(self):
        self.assertContains(self.resposta, "Oficina de Git")
        self.assertContains(self.resposta, "Sala: Sala 1 - A")
        self.assertContains(self.resposta, "1 de 1 vagas disponíveis")

    def test_programacao_nao_mostra_atividade_de_outro_evento(self):
        self.assertNotContains(self.resposta, "Sarau")

    def test_contexto_traz_o_evento_e_as_atividades_em_ordem_de_inicio(self):
        self.assertEqual(self.resposta.context["evento"], self.evento)
        self.assertEqual(
            [atividade.pk for atividade in self.resposta.context["atividades"]],
            [self.atividade.pk, self.simultanea.pk, self.seguinte.pk],
        )

    def test_contexto_de_anonimo_nao_tem_inscricao_nem_gerencia(self):
        self.assertIsNone(self.resposta.context["inscricao"])
        self.assertFalse(self.resposta.context["pode_gerenciar"])


class ConsultasDaProgramacaoTests(CenarioRegras):
    def test_programacao_do_site_faz_as_mesmas_consultas_com_mais_atividades(self):
        endereco = url("detalhe", self.evento)
        with self.assertNumQueries(2):
            self.client.get(endereco)
        sala_extra = criar_sala("Sala 3", 10)
        for indice in range(10):
            criar_atividade(self.evento, sala_extra, f"Extra {indice}", horario(12 + indice), horario(12 + indice, 30))
        with self.assertNumQueries(2):
            resposta = self.client.get(endereco)
        self.assertEqual(len(resposta.context["atividades"]), 13)


class InscricaoECancelamentoTests(CenarioRegras):
    def test_inscrever_no_evento_grava_redireciona_e_confirma(self):
        self.client.force_login(self.sem_inscricao)
        resposta = self.client.post(url("inscrever_evento", self.evento), follow=True)
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        self.assertEqual(mensagens(resposta), ["Inscrição no evento confirmada. Escolha suas atividades."])
        self.assertTrue(InscricaoEvento.objects.filter(evento=self.evento, participante=self.sem_inscricao).exists())

    def test_inscrever_no_evento_repetido_nao_duplica_redireciona_e_avisa(self):
        self.client.force_login(self.participante)
        resposta = self.client.post(url("inscrever_evento", self.evento), follow=True)
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        self.assertEqual(mensagens(resposta), ["Você já está inscrito neste evento."])
        self.assertEqual(InscricaoEvento.objects.filter(evento=self.evento, participante=self.participante).count(), 1)

    def test_inscrever_na_atividade_grava_redireciona_e_confirma(self):
        self.client.force_login(self.participante)
        resposta = self.client.post(url("inscrever_atividade", self.atividade), follow=True)
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        self.assertEqual(mensagens(resposta), ["Inscrição na atividade confirmada."])
        self.assertTrue(self.atividade.inscricoes.filter(inscricao_evento=self.inscricao).exists())

    def test_inscrever_na_atividade_recusada_redireciona_e_avisa(self):
        ocupar(self.inscricao_colega, self.atividade)
        self.client.force_login(self.participante)
        resposta = self.client.post(url("inscrever_atividade", self.atividade), follow=True)
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        self.assertEqual(mensagens(resposta), ["Esta atividade está lotada."])

    def test_cancelar_inscricao_no_evento_apaga_redireciona_e_confirma(self):
        pk = self.inscricao.pk
        self.client.force_login(self.participante)
        resposta = self.client.post(url("cancelar_evento", self.inscricao), follow=True)
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        self.assertEqual(mensagens(resposta), ["Inscrição no evento e em suas atividades cancelada."])
        self.assertFalse(InscricaoEvento.objects.filter(pk=pk).exists())

    def test_cancelar_inscricao_na_atividade_apaga_redireciona_e_confirma(self):
        inscricao = ocupar(self.inscricao, self.atividade)
        pk = inscricao.pk
        self.client.force_login(self.participante)
        resposta = self.client.post(url("cancelar_atividade", inscricao), follow=True)
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        self.assertEqual(mensagens(resposta), ["Inscrição na atividade cancelada."])
        self.assertFalse(InscricaoAtividade.objects.filter(pk=pk).exists())
        self.assertTrue(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())


class AnonimoNoSiteTests(CenarioRegras):
    def assertVaiParaLoginComNext(self, resposta, endereco):
        self.assertRedirects(resposta, f"{reverse('login')}?next={endereco}")

    def test_anonimo_na_agenda_vai_para_o_login_com_next(self):
        endereco = reverse("eventos:agenda")
        self.assertVaiParaLoginComNext(self.client.get(endereco), endereco)

    def test_anonimo_em_novo_evento_vai_para_o_login_com_next(self):
        endereco = reverse("eventos:novo")
        self.assertVaiParaLoginComNext(self.client.get(endereco), endereco)

    def test_anonimo_ao_editar_evento_vai_para_o_login_com_next(self):
        endereco = url("editar", self.evento)
        self.assertVaiParaLoginComNext(self.client.get(endereco), endereco)

    def test_anonimo_ao_inscrever_no_evento_vai_para_o_login_com_next_e_nada_e_gravado(self):
        endereco = url("inscrever_evento", self.evento)
        total = InscricaoEvento.objects.count()
        self.assertVaiParaLoginComNext(self.client.post(endereco), endereco)
        self.assertEqual(InscricaoEvento.objects.count(), total)

    def test_anonimo_ao_inscrever_na_atividade_vai_para_o_login_com_next_e_nada_e_gravado(self):
        endereco = url("inscrever_atividade", self.atividade)
        self.assertVaiParaLoginComNext(self.client.post(endereco), endereco)
        self.assertFalse(self.atividade.inscricoes.exists())

    def test_anonimo_ao_cancelar_vai_para_o_login_com_next_e_a_inscricao_continua(self):
        endereco = url("cancelar_evento", self.inscricao)
        self.assertVaiParaLoginComNext(self.client.post(endereco), endereco)
        self.assertTrue(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())


class AutorizacaoNoSiteTests(CenarioRegras):
    def dados_evento(self, **alteracoes):
        dados = {
            "nome": "Nome alterado", "descricao": "Outra descrição.",
            "data_inicio": "2030-03-04", "data_fim": "2030-03-06", "inscricoes_abertas": "on",
        }
        dados.update(alteracoes)
        return dados

    def assertEventoIntacto(self):
        nome = self.evento.nome
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.nome, nome)

    def test_participante_nao_cria_evento(self):
        total = Evento.objects.count()
        self.client.force_login(self.participante)
        resposta = self.client.post(reverse("eventos:novo"), self.dados_evento())
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(Evento.objects.count(), total)

    def test_participante_nao_edita_evento(self):
        self.client.force_login(self.participante)
        resposta = self.client.post(url("editar", self.evento), self.dados_evento())
        self.assertEqual(resposta.status_code, 403)
        self.assertEventoIntacto()

    def test_organizador_nao_edita_evento_de_outro_organizador(self):
        self.client.force_login(self.outro_organizador)
        resposta = self.client.post(url("editar", self.evento), self.dados_evento())
        self.assertEqual(resposta.status_code, 403)
        self.assertEventoIntacto()

    def test_organizador_nao_exclui_evento_de_outro_organizador(self):
        self.client.force_login(self.outro_organizador)
        resposta = self.client.post(url("excluir", self.evento))
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(Evento.objects.filter(pk=self.evento.pk).exists())

    def test_organizador_edita_o_proprio_evento(self):
        self.client.force_login(self.organizador)
        resposta = self.client.post(url("editar", self.evento), self.dados_evento())
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.nome, "Nome alterado")

    def test_ninguem_cancela_inscricao_no_evento_que_nao_e_sua(self):
        self.client.force_login(self.colega)
        resposta = self.client.post(url("cancelar_evento", self.inscricao))
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())

    def test_ninguem_cancela_inscricao_em_atividade_que_nao_e_sua(self):
        inscricao = ocupar(self.inscricao, self.atividade)
        self.client.force_login(self.colega)
        resposta = self.client.post(url("cancelar_atividade", inscricao))
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(InscricaoAtividade.objects.filter(pk=inscricao.pk).exists())


class SiteComDadosDeCadastroTests(DadosDeCadastro):
    def entrar(self, usuario):
        self.client.force_login(usuario)

    def dados_atividade(self, **alteracoes):
        dados = {
            "titulo": "Nova palestra", "tipo": "PA", "descricao": "Uma palestra.",
            "responsavel": "Maria", "sala": self.auditorio.pk,
            "inicio": "2026-10-21T08:00", "fim": "2026-10-21T09:00",
        }
        dados.update(alteracoes)
        return dados

    def test_programacao_publica_e_vagas(self):
        self.assertEqual(self.client.get(reverse("eventos:lista")).status_code, 200)
        resposta = self.client.get(url("detalhe", self.evento))
        self.assertContains(resposta, "Django na prática")
        self.assertContains(resposta, "Ana Souza")
        self.assertContains(resposta, "1 de 2 vagas disponíveis")
        self.assertNotContains(resposta, url("inscrever_atividade", self.atividade))
        self.assertEqual(
            [atividade.pk for atividade in resposta.context["atividades"]],
            [self.atividade.pk, self.conflito_interno.pk, self.seguinte.pk],
        )

    def test_anonimo_precisa_de_login(self):
        for endereco in [
            url("inscrever_evento", self.evento), url("inscrever_atividade", self.atividade),
            reverse("eventos:agenda"), reverse("eventos:novo"),
        ]:
            resposta = self.client.post(endereco)
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
        for endereco in [
            reverse("eventos:novo"), url("editar", self.evento), url("excluir", self.evento),
            url("painel", self.evento), reverse("eventos:nova_atividade", args=[self.evento.pk]),
            url("editar_atividade", self.atividade),
        ]:
            self.assertEqual(self.client.get(endereco).status_code, 403)
            self.assertEqual(self.client.post(endereco, {}).status_code, 403)

    def test_propriedade_em_todas_as_rotas_de_organizador(self):
        self.entrar(self.outro_organizador)
        for nome, objeto in [
            ("editar", self.evento), ("excluir", self.evento), ("painel", self.evento),
            ("nova_atividade", self.evento), ("editar_atividade", self.atividade),
            ("excluir_atividade", self.atividade),
        ]:
            self.assertEqual(self.client.get(url(nome, objeto)).status_code, 403)
            if nome != "painel":
                self.assertEqual(self.client.post(url(nome, objeto), {}).status_code, 403)
        resposta = self.client.get(url("detalhe", self.evento))
        self.assertNotContains(resposta, url("editar", self.evento))
        self.assertNotContains(resposta, url("painel", self.evento))

    def test_atividade_fora_do_periodo_ou_intervalo_invalido(self):
        self.entrar(self.organizador)
        for inicio, fim in [
            ("2026-10-18T10:00", "2026-10-18T11:00"),
            ("2026-10-21T23:30", "2026-10-22T00:30"),
            ("2026-10-21T09:00", "2026-10-21T08:00"),
            ("2026-10-21T09:00", "2026-10-21T09:00"),
        ]:
            resposta = self.client.post(url("nova_atividade", self.evento), self.dados_atividade(
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
            resposta = self.client.post(url("nova_atividade", self.outro_evento), self.dados_atividade(
                sala=self.atividade.sala_id,
                inicio=f"2026-10-19T{inicio}", fim=f"2026-10-19T{fim}",
            ))
            self.assertContains(resposta, "A sala já está ocupada nesse horário.")
        self.assertFalse(Atividade.objects.filter(titulo="Nova palestra").exists())

    def test_atividade_adjacente_na_mesma_sala_e_edicao_propria(self):
        self.entrar(self.organizador)
        resposta = self.client.post(url("nova_atividade", self.evento), self.dados_atividade(
            sala=self.atividade.sala_id, inicio="2026-10-19T11:00", fim="2026-10-19T12:00"
        ))
        self.assertRedirects(resposta, self.evento.get_absolute_url())
        nova = Atividade.objects.get(titulo="Nova palestra")
        resposta = self.client.post(url("editar_atividade", nova), self.dados_atividade(
            sala=nova.sala_id, inicio="2026-10-19T11:00", fim="2026-10-19T12:00"
        ))
        self.assertRedirects(resposta, self.evento.get_absolute_url())

    def test_sala_ocupada_tambem_impede_edicao(self):
        self.entrar(self.organizador)
        resposta = self.client.post(url("editar_atividade", self.seguinte), self.dados_atividade(
            sala=self.atividade.sala_id, inicio="2026-10-19T09:00", fim="2026-10-19T10:00"
        ))
        self.assertContains(resposta, "A sala já está ocupada nesse horário.")
        self.seguinte.refresh_from_db()
        self.assertEqual(timezone.localtime(self.seguinte.inicio).hour, 10)

    def test_inscricao_evento_duplicada_e_fechada(self):
        self.entrar(self.terceiro)
        self.assertRedirects(self.client.post(url("inscrever_evento", self.evento)), self.evento.get_absolute_url())
        self.client.post(url("inscrever_evento", self.evento))
        self.assertEqual(InscricaoEvento.objects.filter(evento=self.evento, participante=self.terceiro).count(), 1)
        resposta = self.client.post(url("inscrever_evento", self.fechado), follow=True)
        self.assertContains(resposta, "As inscrições deste evento estão fechadas.")
        self.assertFalse(InscricaoEvento.objects.filter(evento=self.fechado, participante=self.terceiro).exists())

    def test_sem_inscricao_no_evento_nao_escolhe_atividade(self):
        self.entrar(self.terceiro)
        resposta = self.client.get(url("detalhe", self.evento))
        self.assertNotContains(resposta, url("inscrever_atividade", self.atividade))
        resposta = self.client.post(url("inscrever_atividade", self.atividade), follow=True)
        self.assertContains(resposta, "Inscreva-se no evento antes de escolher uma atividade.")
        self.assertFalse(InscricaoAtividade.objects.filter(inscricao_evento__participante=self.terceiro).exists())

    def test_limite_de_vagas_e_interface_lotada(self):
        self.entrar(self.outro_participante)
        self.client.post(url("inscrever_atividade", self.atividade))
        self.assertEqual(self.atividade.inscricoes.count(), 2)
        self.client.post(url("inscrever_atividade", self.atividade))
        self.assertEqual(self.atividade.inscricoes.count(), 2)
        self.entrar(self.terceiro)
        self.client.post(url("inscrever_evento", self.evento))
        resposta = self.client.post(url("inscrever_atividade", self.atividade), follow=True)
        self.assertContains(resposta, "Esta atividade está lotada.")
        self.assertContains(resposta, "0 de 2 vagas disponíveis")
        self.assertNotContains(resposta, url("inscrever_atividade", self.atividade))
        self.assertEqual(self.atividade.inscricoes.count(), 2)

    def test_conflitos_da_agenda_dentro_e_fora_do_evento(self):
        self.entrar(self.participante)
        for atividade in [self.conflito_interno, self.conflito_externo]:
            resposta = self.client.get(url("detalhe", atividade.evento))
            self.assertNotContains(resposta, url("inscrever_atividade", atividade))
            resposta = self.client.post(url("inscrever_atividade", atividade), follow=True)
            self.assertContains(resposta, "Esta atividade conflita com outra inscrição na sua agenda.")
            self.assertFalse(atividade.inscricoes.exists())

    def test_atividade_adjacente_nao_conflita_com_agenda(self):
        self.entrar(self.participante)
        self.client.post(url("inscrever_atividade", self.seguinte))
        self.assertTrue(self.seguinte.inscricoes.filter(inscricao_evento=self.inscricao).exists())

    def test_cancelar_atividade_libera_vaga_e_preserva_evento(self):
        self.entrar(self.participante)
        inscricao = self.atividade.inscricoes.get(inscricao_evento=self.inscricao)
        self.client.post(url("cancelar_atividade", inscricao))
        self.assertTrue(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())
        self.assertFalse(InscricaoAtividade.objects.filter(pk=inscricao.pk).exists())
        self.assertContains(self.client.get(url("detalhe", self.evento)), "2 de 2 vagas disponíveis")

    def test_cancelar_evento_remove_suas_atividades(self):
        self.entrar(self.participante)
        self.client.post(url("inscrever_atividade", self.seguinte))
        self.client.post(url("cancelar_evento", self.inscricao))
        self.assertFalse(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())
        self.assertFalse(InscricaoAtividade.objects.filter(inscricao_evento_id=self.inscricao.pk).exists())
        self.assertTrue(self.posterior.inscricoes.filter(inscricao_evento__participante=self.participante).exists())

    def test_nao_cancela_inscricao_alheia(self):
        self.entrar(self.outro_participante)
        inscricao = self.atividade.inscricoes.get(inscricao_evento=self.inscricao)
        for nome, objeto in [("cancelar_evento", self.inscricao), ("cancelar_atividade", inscricao)]:
            self.assertEqual(self.client.post(url(nome, objeto)).status_code, 403)
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
        resposta = self.client.get(url("painel", self.evento))
        self.assertContains(resposta, "participante4")
        self.assertContains(resposta, "1 inscritos")
        self.assertContains(resposta, "1 vagas restantes")
        self.assertNotContains(resposta, "Comunicação científica")
        self.assertEqual(self.client.get(url("painel", self.outro_evento)).status_code, 403)

    def test_mutacoes_exigem_post_e_csrf(self):
        self.entrar(self.participante)
        inscricao = self.atividade.inscricoes.get(inscricao_evento=self.inscricao)
        enderecos = [
            url("inscrever_evento", self.outro_evento), url("inscrever_atividade", self.seguinte),
            url("cancelar_evento", self.inscricao), url("cancelar_atividade", inscricao),
        ]
        cliente_csrf = Client(enforce_csrf_checks=True)
        cliente_csrf.force_login(self.participante)
        for endereco in enderecos:
            self.assertEqual(self.client.get(endereco).status_code, 405)
            self.assertEqual(cliente_csrf.post(endereco).status_code, 403)
        self.assertTrue(InscricaoAtividade.objects.filter(pk=inscricao.pk).exists())

    def test_exclusao_so_no_post(self):
        self.entrar(self.organizador)
        self.assertEqual(self.client.get(url("excluir_atividade", self.seguinte)).status_code, 200)
        self.assertTrue(Atividade.objects.filter(pk=self.seguinte.pk).exists())
        self.assertRedirects(self.client.post(url("excluir_atividade", self.seguinte)), self.evento.get_absolute_url())
        self.assertFalse(Atividade.objects.filter(pk=self.seguinte.pk).exists())
        self.assertEqual(self.client.get(url("excluir", self.evento)).status_code, 200)
        self.assertTrue(Evento.objects.filter(pk=self.evento.pk).exists())
        self.assertRedirects(self.client.post(url("excluir", self.evento)), reverse("eventos:lista"))
        self.assertFalse(Atividade.objects.filter(evento_id=self.evento.pk).exists())
        self.assertFalse(InscricaoEvento.objects.filter(evento_id=self.evento.pk).exists())

    def test_admin_entidades_registradas_e_dados_excluidos_dos_forms(self):
        self.entrar(User.objects.get(username="admin"))
        for model in ["sala", "evento", "atividade", "inscricaoevento", "inscricaoatividade"]:
            self.assertEqual(self.client.get(reverse(f"admin:inscricoes_{model}_changelist")).status_code, 200)
        resposta = self.client.get(reverse("admin:inscricoes_evento_add"))
        self.assertNotContains(resposta, 'name="organizador"')
        resposta = self.client.get(reverse("admin:inscricoes_inscricaoevento_add"))
        self.assertNotContains(resposta, 'name="participante"')

    def test_dados_de_teste_podem_ser_cadastrados_novamente(self):
        cadastrar_dados()
        self.assertEqual(Evento.objects.count(), 3)
        self.assertEqual(Atividade.objects.count(), 5)
        self.assertEqual(Sala.objects.count(), 3)
