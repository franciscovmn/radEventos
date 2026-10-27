from django.urls import path
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from . import views


app_name = "api"
router = DefaultRouter()
router.register("salas", views.SalaViewSet)
router.register("eventos", views.EventoViewSet)
router.register("atividades", views.AtividadeViewSet, basename="atividade")
router.register("inscricoes/eventos", views.InscricaoEventoViewSet, basename="inscricao-evento")
router.register("inscricoes/atividades", views.InscricaoAtividadeViewSet, basename="inscricao-atividade")
urlpatterns = [
    path("token/", views.obter_token, name="token"),
    path("eventos/<int:evento_id>/programacao/", views.programacao_evento, name="programacao-evento"),
    path("agenda/", views.agenda_participante, name="agenda-participante"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
] + router.urls
