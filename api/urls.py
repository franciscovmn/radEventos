from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views


app_name = "api"
router = DefaultRouter()
router.register("salas", views.SalaViewSet)
router.register("eventos", views.EventoViewSet)
router.register("atividades", views.AtividadeViewSet, basename="atividade")
urlpatterns = [path("token/", views.obter_token, name="token")] + router.urls
