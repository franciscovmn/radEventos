from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Atividade, Evento, InscricaoAtividade, InscricaoEvento


def obter_agenda_participante(participante):
    return InscricaoAtividade.objects.filter(
        inscricao_evento__participante=participante
    ).select_related("atividade__evento", "atividade__sala").order_by("atividade__inicio", "pk")


def obter_dados_evento(evento, usuario):
    inscricao = None
    escolhidas = {}
    agenda = []
    if usuario.is_authenticated:
        inscricao = evento.inscricoes.filter(participante=usuario).first()
        if inscricao:
            escolhidas = dict(inscricao.inscricoes_atividades.values_list("atividade_id", "pk"))
        agenda = list(InscricaoAtividade.objects.filter(
            inscricao_evento__participante=usuario
        ).select_related("atividade"))

    atividades = list(evento.atividades.com_vagas())
    for atividade in atividades:
        atividade.dias_diferentes = (
            timezone.localtime(atividade.inicio).date() != timezone.localtime(atividade.fim).date()
        )
        atividade.inscricao_id = escolhidas.get(atividade.pk)
        atividade.conflito = any(
            item.atividade_id != atividade.pk
            and item.atividade.inicio < atividade.fim
            and item.atividade.fim > atividade.inicio
            for item in agenda
        )
        atividade.pode_inscrever = bool(
            inscricao and not atividade.inscricao_id
            and atividade.vagas_restantes > 0 and not atividade.conflito
        )
    return {
        "atividades": atividades,
        "inscricao": inscricao,
        "pode_gerenciar": evento.pode_ser_gerenciado_por(usuario),
    }


def inscrever_no_evento(usuario, evento_pk):
    with transaction.atomic():
        evento = get_object_or_404(Evento, pk=evento_pk)
        if evento.inscricoes.filter(participante=usuario).exists():
            raise ValidationError("Você já está inscrito neste evento.")
        return InscricaoEvento.objects.create(evento=evento, participante=usuario)


def inscrever_em_atividade(usuario, atividade_pk):
    with transaction.atomic():
        atividade = get_object_or_404(Atividade.objects.select_related("evento", "sala"), pk=atividade_pk)
        inscricao = InscricaoEvento.objects.filter(evento=atividade.evento, participante=usuario).first()
        if inscricao is None:
            raise ValidationError("Inscreva-se no evento antes de escolher uma atividade.")
        if atividade.inscricoes.filter(inscricao_evento=inscricao).exists():
            raise ValidationError("Você já está inscrito nesta atividade.")
        return InscricaoAtividade.objects.create(inscricao_evento=inscricao, atividade=atividade)


def cancelar_inscricao_no_evento(usuario, inscricao_pk):
    with transaction.atomic():
        inscricao = get_object_or_404(InscricaoEvento.objects.select_related("evento"), pk=inscricao_pk)
        if inscricao.participante_id != usuario.pk:
            raise PermissionDenied
        inscricao.delete()
        return inscricao.evento


def cancelar_inscricao_em_atividade(usuario, inscricao_pk):
    with transaction.atomic():
        inscricao = get_object_or_404(
            InscricaoAtividade.objects.select_related("inscricao_evento", "atividade__evento"), pk=inscricao_pk
        )
        if inscricao.inscricao_evento.participante_id != usuario.pk:
            raise PermissionDenied
        inscricao.delete()
        return inscricao.atividade.evento
