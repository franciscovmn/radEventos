from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import Atividade, Evento, InscricaoAtividade, InscricaoEvento


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
