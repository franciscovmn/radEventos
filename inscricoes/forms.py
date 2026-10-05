from django import forms

from .models import Atividade, Evento


class EventoForm(forms.ModelForm):
    class Meta:
        model = Evento
        fields = ["nome", "descricao", "data_inicio", "data_fim", "inscricoes_abertas"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "data_inicio": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "data_fim": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }


class AtividadeForm(forms.ModelForm):
    class Meta:
        model = Atividade
        fields = ["titulo", "tipo", "descricao", "responsavel", "sala", "inicio", "fim"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 4}),
            "inicio": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
            "fim": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        }
