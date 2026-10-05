from django.urls import path

from . import views


app_name = "eventos"
urlpatterns = [
    path("", views.EventoListView.as_view(), name="lista"),
    path("eventos/novo/", views.EventoCreateView.as_view(), name="novo"),
    path("eventos/<int:pk>/", views.EventoDetailView.as_view(), name="detalhe"),
    path("eventos/<int:pk>/editar/", views.EventoUpdateView.as_view(), name="editar"),
    path("eventos/<int:pk>/excluir/", views.EventoDeleteView.as_view(), name="excluir"),
    path("eventos/<int:pk>/inscrever/", views.inscrever_evento, name="inscrever_evento"),
    path("eventos/<int:evento_pk>/atividades/nova/", views.AtividadeCreateView.as_view(), name="nova_atividade"),
    path("atividades/<int:pk>/editar/", views.AtividadeUpdateView.as_view(), name="editar_atividade"),
    path("atividades/<int:pk>/excluir/", views.AtividadeDeleteView.as_view(), name="excluir_atividade"),
    path("atividades/<int:pk>/inscrever/", views.inscrever_atividade, name="inscrever_atividade"),
    path("inscricoes/eventos/<int:pk>/cancelar/", views.cancelar_evento, name="cancelar_evento"),
    path("inscricoes/atividades/<int:pk>/cancelar/", views.cancelar_atividade, name="cancelar_atividade"),
]
