from django.contrib import admin

from .models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ["nome", "bloco", "capacidade"]
    list_filter = ["bloco"]
    search_fields = ["nome", "bloco"]


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ["nome", "data_inicio", "data_fim", "inscricoes_abertas", "organizador"]
    list_filter = ["inscricoes_abertas", "data_inicio"]
    search_fields = ["nome", "descricao", "organizador__username"]
    exclude = ["organizador"]

    def get_form(self, request, obj=None, **kwargs):
        formulario = super().get_form(request, obj, **kwargs)

        class FormularioEvento(formulario):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if self.instance._state.adding:
                    self.instance.organizador = request.user

        return FormularioEvento

    def save_model(self, request, obj, form, change):
        if not change:
            obj.organizador = request.user
        super().save_model(request, obj, form, change)


@admin.register(Atividade)
class AtividadeAdmin(admin.ModelAdmin):
    list_display = ["titulo", "evento", "tipo", "sala", "inicio", "fim"]
    list_filter = ["evento", "tipo", "sala"]
    search_fields = ["titulo", "responsavel", "evento__nome"]
    list_select_related = ["evento", "sala"]


@admin.register(InscricaoEvento)
class InscricaoEventoAdmin(admin.ModelAdmin):
    list_display = ["evento", "participante", "data"]
    list_filter = ["evento", "data"]
    search_fields = ["evento__nome", "participante__username"]
    list_select_related = ["evento", "participante"]
    exclude = ["participante"]
    readonly_fields = ["data"]

    def get_form(self, request, obj=None, **kwargs):
        formulario = super().get_form(request, obj, **kwargs)

        class FormularioInscricao(formulario):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if self.instance._state.adding:
                    self.instance.participante = request.user

        return FormularioInscricao

    def save_model(self, request, obj, form, change):
        if not change:
            obj.participante = request.user
        super().save_model(request, obj, form, change)


@admin.register(InscricaoAtividade)
class InscricaoAtividadeAdmin(admin.ModelAdmin):
    list_display = ["atividade", "inscricao_evento", "data"]
    list_filter = ["atividade__evento", "atividade"]
    search_fields = ["atividade__titulo", "inscricao_evento__participante__username"]
    list_select_related = ["atividade", "inscricao_evento__participante", "inscricao_evento__evento"]
    readonly_fields = ["data"]
