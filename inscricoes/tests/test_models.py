from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from inscricoes.models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala

from .base import CenarioRegras, DadosDeCadastro, criar_evento, criar_organizador, criar_sala, horario, ocupar


class RegrasNoModelTests(CenarioRegras):
    def nova_inscricao(self, inscricao, atividade):
        return InscricaoAtividade(inscricao_evento=inscricao, atividade=atividade)

    def nova_atividade(self, sala, inicio, fim):
        return Atividade(
            evento=self.evento, sala=sala, titulo="Nova", tipo=Atividade.Tipo.PALESTRA,
            descricao="Nova atividade.", responsavel="Joana", inicio=inicio, fim=fim,
        )

    def test_regra1_aceita_inscricao_enquanto_ha_vaga(self):
        ocupar(self.inscricao, self.atividade)
        self.assertEqual(self.atividade.inscricoes.count(), 1)

    def test_regra1_recusa_inscricao_alem_da_capacidade(self):
        ocupar(self.inscricao_colega, self.atividade)
        with self.assertRaisesMessage(ValidationError, "Esta atividade está lotada."):
            self.nova_inscricao(self.inscricao, self.atividade).full_clean()

    def test_regra2_aceita_atividade_que_comeca_quando_a_outra_termina(self):
        ocupar(self.inscricao, self.simultanea)
        ocupar(self.inscricao, self.seguinte)
        self.assertEqual(self.inscricao.inscricoes_atividades.count(), 2)

    def test_regra2_recusa_atividade_em_horario_sobreposto(self):
        ocupar(self.inscricao, self.atividade)
        with self.assertRaisesMessage(ValidationError, "Esta atividade conflita com outra inscrição na sua agenda."):
            self.nova_inscricao(self.inscricao, self.simultanea).full_clean()

    def test_regra3_aceita_mesma_sala_em_horario_livre(self):
        nova = self.nova_atividade(self.sala, horario(10), horario(11))
        nova.save()
        self.assertTrue(Atividade.objects.filter(pk=nova.pk).exists())

    def test_regra3_recusa_mesma_sala_em_horario_sobreposto(self):
        with self.assertRaises(ValidationError) as contexto:
            self.nova_atividade(self.sala, horario(9, 30), horario(10, 30)).full_clean()
        self.assertEqual(contexto.exception.message_dict["sala"], ["A sala já está ocupada nesse horário."])

    def test_regra4_aceita_inscricao_vinda_do_mesmo_evento(self):
        ocupar(self.inscricao, self.seguinte)
        self.assertTrue(self.seguinte.inscricoes.filter(inscricao_evento=self.inscricao).exists())

    def test_regra4_recusa_inscricao_vinda_de_outro_evento(self):
        with self.assertRaisesMessage(ValidationError, "A inscrição precisa ser do mesmo evento da atividade."):
            self.nova_inscricao(self.inscricao, self.de_outro_evento).full_clean()

    def test_regra5_apagar_inscricao_no_evento_apaga_as_das_atividades(self):
        ocupar(self.inscricao, self.atividade)
        ocupar(self.inscricao, self.seguinte)
        pk = self.inscricao.pk
        self.inscricao.delete()
        self.assertFalse(InscricaoAtividade.objects.filter(inscricao_evento_id=pk).exists())

    def test_regra5_apagar_inscricao_na_atividade_nao_apaga_a_do_evento(self):
        inscricao = ocupar(self.inscricao, self.atividade)
        inscricao.delete()
        self.assertTrue(InscricaoEvento.objects.filter(pk=self.inscricao.pk).exists())


class ValidacaoDosModelsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizador = criar_organizador("organizadora")
        cls.sala = criar_sala("Sala 1", 5)
        cls.evento = criar_evento(cls.organizador)

    def evento_novo(self, **alteracoes):
        dados = {
            "nome": "Congresso", "descricao": "Um congresso.", "data_inicio": date(2030, 5, 1),
            "data_fim": date(2030, 5, 2), "organizador": self.organizador,
        }
        dados.update(alteracoes)
        return Evento(**dados)

    def atividade_nova(self, **alteracoes):
        dados = {
            "evento": self.evento, "sala": self.sala, "titulo": "Oficina", "tipo": Atividade.Tipo.TREINAMENTO,
            "descricao": "Uma oficina.", "responsavel": "Joana", "inicio": horario(9), "fim": horario(10),
        }
        dados.update(alteracoes)
        return Atividade(**dados)

    def assertCampoInvalido(self, objeto, campo):
        with self.assertRaises(ValidationError) as contexto:
            objeto.full_clean()
        self.assertIn(campo, contexto.exception.message_dict)

    def test_evento_com_dados_validos_passa_e_e_gravado(self):
        evento = self.evento_novo()
        evento.full_clean()
        evento.save()
        self.assertEqual(Evento.objects.get(pk=evento.pk).nome, "Congresso")

    def test_evento_com_fim_antes_do_inicio_e_recusado(self):
        self.assertCampoInvalido(self.evento_novo(data_fim=date(2030, 4, 30)), "data_fim")

    def test_evento_sem_nome_e_recusado(self):
        self.assertCampoInvalido(self.evento_novo(nome=""), "nome")

    def test_evento_sem_descricao_e_recusado(self):
        self.assertCampoInvalido(self.evento_novo(descricao=""), "descricao")

    def test_atividade_com_fim_antes_do_inicio_e_recusada(self):
        self.assertCampoInvalido(self.atividade_nova(inicio=horario(10), fim=horario(9)), "fim")

    def test_atividade_com_fim_igual_ao_inicio_e_recusada(self):
        self.assertCampoInvalido(self.atividade_nova(inicio=horario(9), fim=horario(9)), "fim")

    def test_atividade_sem_titulo_e_recusada(self):
        self.assertCampoInvalido(self.atividade_nova(titulo=""), "titulo")

    def test_atividade_com_tipo_fora_das_opcoes_e_recusada(self):
        self.assertCampoInvalido(self.atividade_nova(tipo="XX"), "tipo")

    def test_atividade_fora_do_periodo_do_evento_e_recusada(self):
        with self.assertRaisesMessage(ValidationError, "A atividade precisa acontecer dentro do período do evento."):
            self.atividade_nova(inicio=horario(9, dia=20), fim=horario(10, dia=20)).full_clean()

    def test_sala_com_capacidade_negativa_e_recusada(self):
        self.assertCampoInvalido(Sala(nome="Sala 2", bloco="B", capacidade=-1), "capacidade")

    def test_sala_com_capacidade_zero_e_recusada(self):
        self.assertCampoInvalido(Sala(nome="Sala 2", bloco="B", capacidade=0), "capacidade")

    def test_sala_sem_bloco_e_recusada(self):
        self.assertCampoInvalido(Sala(nome="Sala 2", bloco="", capacidade=10), "bloco")

    def test_save_valida_e_nao_grava_dado_invalido(self):
        with self.assertRaises(ValidationError):
            self.evento_novo(nome="").save()
        self.assertEqual(Evento.objects.count(), 1)


class EdicaoComInscritosTests(DadosDeCadastro):
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


class AtividadeComVagasTests(CenarioRegras):
    def test_com_vagas_desconta_os_inscritos_da_capacidade_da_sala(self):
        ocupar(self.inscricao, self.seguinte)
        atividade = Atividade.objects.com_vagas().get(pk=self.seguinte.pk)
        self.assertEqual(atividade.total_inscritos, 1)
        self.assertEqual(atividade.vagas_restantes, 9)

    def test_sobrepostas_nao_inclui_atividade_que_so_encosta_no_intervalo(self):
        encontradas = Atividade.objects.sobrepostas(horario(10), horario(10, 30))
        self.assertEqual(list(encontradas), [self.simultanea])
