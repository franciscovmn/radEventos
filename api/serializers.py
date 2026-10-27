from rest_framework import serializers

from inscricoes import servicos
from inscricoes.models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala


class SalaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sala
        fields = ["id", "nome", "bloco", "capacidade"]


class EventoSerializer(serializers.ModelSerializer):
    organizador = serializers.CharField(source="organizador.username", read_only=True)

    class Meta:
        model = Evento
        fields = ["id", "nome", "descricao", "data_inicio", "data_fim", "inscricoes_abertas", "organizador"]


class AtividadeSerializer(serializers.ModelSerializer):
    sala_nome = serializers.CharField(source="sala.nome", read_only=True)
    vagas_restantes = serializers.SerializerMethodField()

    class Meta:
        model = Atividade
        fields = [
            "id", "evento", "titulo", "tipo", "descricao", "responsavel",
            "sala", "sala_nome", "inicio", "fim", "vagas_restantes",
        ]

    def get_vagas_restantes(self, atividade) -> int:
        if hasattr(atividade, "vagas_restantes"):
            return atividade.vagas_restantes
        return atividade.sala.capacidade - atividade.inscricoes.count()

    def validate_evento(self, evento):
        if self.instance is not None and evento != self.instance.evento:
            raise serializers.ValidationError("Uma atividade não pode mudar de evento.")
        return evento



class InscricaoEventoSerializer(serializers.ModelSerializer):
    participante = serializers.CharField(source="participante.username", read_only=True)

    class Meta:
        model = InscricaoEvento
        fields = ["id", "evento", "participante", "data"]
        validators = []

    def create(self, validated_data):
        return servicos.inscrever_no_evento(self.context["request"].user, validated_data["evento"].pk)


class InscricaoAtividadeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InscricaoAtividade
        fields = ["id", "atividade", "inscricao_evento", "data"]
        read_only_fields = ["inscricao_evento"]
        validators = []

    def create(self, validated_data):
        return servicos.inscrever_em_atividade(self.context["request"].user, validated_data["atividade"].pk)
