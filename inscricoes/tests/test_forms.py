from datetime import date

from django.test import TestCase

from inscricoes.forms import AtividadeForm, EventoForm
from inscricoes.models import Atividade, Evento

from .base import criar_atividade, criar_evento, criar_organizador, criar_sala, horario


class EventoFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizador = criar_organizador("organizadora")

    def formulario(self, **alteracoes):
        dados = {
            "nome": "Congresso", "descricao": "Um congresso.", "data_inicio": "2030-05-01",
            "data_fim": "2030-05-02", "inscricoes_abertas": "on",
        }
        dados.update(alteracoes)
        return EventoForm(data=dados, instance=Evento(organizador=self.organizador))

    def test_dados_validos_chegam_convertidos_em_cleaned_data(self):
        formulario = self.formulario()
        self.assertTrue(formulario.is_valid())
        self.assertEqual(formulario.errors, {})
        self.assertEqual(formulario.cleaned_data["nome"], "Congresso")
        self.assertEqual(formulario.cleaned_data["data_inicio"], date(2030, 5, 1))
        self.assertEqual(formulario.cleaned_data["data_fim"], date(2030, 5, 2))
        self.assertIs(formulario.cleaned_data["inscricoes_abertas"], True)

    def test_fim_antes_do_inicio_aponta_o_erro_no_campo_data_fim(self):
        formulario = self.formulario(data_fim="2030-04-30")
        self.assertFalse(formulario.is_valid())
        self.assertEqual(formulario.errors, {"data_fim": ["A data de fim não pode vir antes do início."]})
        self.assertNotIn("data_fim", formulario.cleaned_data)
        self.assertEqual(formulario.cleaned_data["nome"], "Congresso")

    def test_nome_vazio_e_campo_obrigatorio(self):
        formulario = self.formulario(nome="")
        self.assertFalse(formulario.is_valid())
        self.assertEqual(formulario.errors, {"nome": ["Este campo é obrigatório."]})
        self.assertNotIn("nome", formulario.cleaned_data)

    def test_organizador_enviado_nos_dados_e_ignorado(self):
        outro = criar_organizador("outra")
        formulario = self.formulario(organizador=outro.pk)
        self.assertTrue(formulario.is_valid())
        self.assertNotIn("organizador", formulario.cleaned_data)
        self.assertEqual(formulario.save().organizador, self.organizador)


class AtividadeFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizador = criar_organizador("organizadora")
        cls.sala = criar_sala("Sala 1", 5)
        cls.evento = criar_evento(cls.organizador)
        cls.existente = criar_atividade(cls.evento, cls.sala, "Oficina", horario(9), horario(10))

    def formulario(self, **alteracoes):
        dados = {
            "titulo": "Palestra", "tipo": "PA", "descricao": "Uma palestra.", "responsavel": "Joana",
            "sala": self.sala.pk, "inicio": "2030-03-04T10:00", "fim": "2030-03-04T11:00",
        }
        dados.update(alteracoes)
        return AtividadeForm(data=dados, instance=Atividade(evento=self.evento))

    def test_dados_validos_chegam_convertidos_em_cleaned_data(self):
        formulario = self.formulario()
        self.assertTrue(formulario.is_valid())
        self.assertEqual(formulario.errors, {})
        self.assertEqual(formulario.cleaned_data["sala"], self.sala)
        self.assertEqual(formulario.cleaned_data["inicio"], horario(10))
        self.assertEqual(formulario.cleaned_data["fim"], horario(11))

    def test_sala_ocupada_aponta_o_erro_no_campo_sala(self):
        formulario = self.formulario(inicio="2030-03-04T09:30", fim="2030-03-04T10:30")
        self.assertFalse(formulario.is_valid())
        self.assertEqual(formulario.errors, {"sala": ["A sala já está ocupada nesse horário."]})
        self.assertNotIn("sala", formulario.cleaned_data)

    def test_fim_antes_do_inicio_aponta_o_erro_no_campo_fim(self):
        formulario = self.formulario(inicio="2030-03-04T11:00", fim="2030-03-04T10:00")
        self.assertFalse(formulario.is_valid())
        self.assertEqual(formulario.errors, {"fim": ["O fim precisa ser depois do início."]})

    def test_horario_fora_do_evento_e_erro_geral_do_formulario(self):
        formulario = self.formulario(inicio="2030-03-20T10:00", fim="2030-03-20T11:00")
        self.assertFalse(formulario.is_valid())
        self.assertEqual(
            formulario.non_field_errors(), ["A atividade precisa acontecer dentro do período do evento."]
        )

    def test_tipo_fora_das_opcoes_e_recusado(self):
        formulario = self.formulario(tipo="XX")
        self.assertFalse(formulario.is_valid())
        self.assertIn("tipo", formulario.errors)
        self.assertNotIn("tipo", formulario.cleaned_data)
