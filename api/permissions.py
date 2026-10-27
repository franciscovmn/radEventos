from rest_framework.permissions import BasePermission

from inscricoes.models import Evento


class OrganizaEventos(BasePermission):
    message = "Apenas organizadores podem gerenciar eventos e atividades."

    def has_permission(self, request, view):
        return request.user.has_perm("inscricoes.organizar_eventos")


class OrganizadorDoEvento(BasePermission):
    message = "Você só pode alterar eventos e atividades que organiza."

    def has_object_permission(self, request, view, obj):
        evento = obj if isinstance(obj, Evento) else obj.evento
        return evento.pode_ser_gerenciado_por(request.user)
