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


class OrganizadorMixin(LoginRequiredMixin, PermissionRequiredMixin):
    permission_required = "inscricoes.organizar_eventos"

    @method_decorator(transaction.atomic)
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class ObjetoDoOrganizadorMixin:
    def get_object(self, queryset=None):
        objeto = super().get_object(queryset)
        evento = objeto if isinstance(objeto, Evento) else objeto.evento
        if evento.organizador_id != self.request.user.pk:
            raise PermissionDenied
        return objeto


class EventoCreateView(OrganizadorMixin, CreateView):
    model = Evento
    form_class = EventoForm
    template_name = "eventos/form.html"
    extra_context = {"titulo_pagina": "Novo evento"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = Evento(organizador=self.request.user)
        return kwargs


class EventoUpdateView(OrganizadorMixin, ObjetoDoOrganizadorMixin, UpdateView):
    model = Evento
    form_class = EventoForm
    template_name = "eventos/form.html"
    extra_context = {"titulo_pagina": "Editar evento"}


class EventoDeleteView(OrganizadorMixin, ObjetoDoOrganizadorMixin, DeleteView):
    model = Evento
    template_name = "eventos/confirmar_exclusao.html"
    success_url = reverse_lazy("eventos:lista")


class AtividadeFormMixin:
    model = Atividade
    form_class = AtividadeForm
    template_name = "eventos/form.html"

    @cached_property
    def evento(self):
        if self.object:
            return self.object.evento
        evento = get_object_or_404(Evento, pk=self.kwargs["evento_pk"])
        if evento.organizador_id != self.request.user.pk:
            raise PermissionDenied
        return evento

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object is None:
            kwargs["instance"] = Atividade(evento=self.evento)
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["evento"] = self.evento
        return contexto

    def get_success_url(self):
        return self.evento.get_absolute_url()


class AtividadeCreateView(OrganizadorMixin, AtividadeFormMixin, CreateView):
    extra_context = {"titulo_pagina": "Nova atividade"}


class AtividadeUpdateView(OrganizadorMixin, ObjetoDoOrganizadorMixin, AtividadeFormMixin, UpdateView):
    extra_context = {"titulo_pagina": "Editar atividade"}


class AtividadeDeleteView(OrganizadorMixin, ObjetoDoOrganizadorMixin, DeleteView):
    model = Atividade
    template_name = "eventos/confirmar_exclusao.html"

    def get_success_url(self):
        return self.object.evento.get_absolute_url()


@login_required
@require_POST
def inscrever_evento(request, pk):
    with transaction.atomic():
        evento = get_object_or_404(Evento, pk=pk)
        if evento.inscricoes.filter(participante=request.user).exists():
            messages.error(request, "Você já está inscrito neste evento.")
        else:
            try:
                InscricaoEvento.objects.create(evento=evento, participante=request.user)
            except ValidationError as erro:
                messages.error(request, " ".join(erro.messages))
            else:
                messages.success(request, "Inscrição no evento confirmada. Escolha suas atividades.")
    return redirect(evento)


@login_required
@require_POST
def inscrever_atividade(request, pk):
    with transaction.atomic():
        atividade = get_object_or_404(Atividade.objects.select_related("evento", "sala"), pk=pk)
        inscricao = InscricaoEvento.objects.filter(
            evento=atividade.evento, participante=request.user
        ).first()
        if inscricao is None:
            messages.error(request, "Inscreva-se no evento antes de escolher uma atividade.")
        elif atividade.inscricoes.filter(inscricao_evento=inscricao).exists():
            messages.error(request, "Você já está inscrito nesta atividade.")
        else:
            try:
                InscricaoAtividade.objects.create(inscricao_evento=inscricao, atividade=atividade)
            except ValidationError as erro:
                messages.error(request, " ".join(erro.messages))
            else:
                messages.success(request, "Inscrição na atividade confirmada.")
    return redirect(atividade.evento)


@login_required
@require_POST
def cancelar_evento(request, pk):
    with transaction.atomic():
        inscricao = get_object_or_404(InscricaoEvento.objects.select_related("evento"), pk=pk)
        if inscricao.participante_id != request.user.pk:
            raise PermissionDenied
        evento = inscricao.evento
        inscricao.delete()
        messages.success(request, "Inscrição no evento e em suas atividades cancelada.")
    return redirect(evento)


@login_required
@require_POST
def cancelar_atividade(request, pk):
    with transaction.atomic():
        inscricao = get_object_or_404(
            InscricaoAtividade.objects.select_related("inscricao_evento", "atividade__evento"), pk=pk
        )
        if inscricao.inscricao_evento.participante_id != request.user.pk:
            raise PermissionDenied
        evento = inscricao.atividade.evento
        inscricao.delete()
        messages.success(request, "Inscrição na atividade cancelada.")
    return redirect(evento)
