from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import AtividadeForm, EventoForm
from .models import Atividade, Evento, InscricaoAtividade, InscricaoEvento


class CadastroView(CreateView):
    form_class = UserCreationForm
    template_name = "registration/cadastro.html"
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        resposta = super().form_valid(form)
        messages.success(self.request, "Conta criada. Entre com seu usuário e senha.")
        return resposta


class EventoListView(ListView):
    model = Evento
    template_name = "eventos/lista.html"
    context_object_name = "eventos"


class EventoDetailView(DetailView):
    model = Evento
    template_name = "eventos/detalhe.html"
    context_object_name = "evento"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        usuario = self.request.user
        inscricao = None
        escolhidas = {}
        agenda = []
        if usuario.is_authenticated:
            inscricao = self.object.inscricoes.filter(participante=usuario).first()
            if inscricao:
                escolhidas = dict(inscricao.inscricoes_atividades.values_list("atividade_id", "pk"))
            agenda = list(InscricaoAtividade.objects.filter(
                inscricao_evento__participante=usuario
            ).select_related("atividade"))

        atividades = list(self.object.atividades.com_vagas())
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

        contexto["atividades"] = atividades
        contexto["inscricao"] = inscricao
        contexto["pode_gerenciar"] = (
            usuario.is_authenticated
            and usuario.has_perm("inscricoes.organizar_eventos")
            and self.object.organizador_id == usuario.pk
        )
        return contexto
