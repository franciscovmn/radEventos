from django.urls import path

from . import views


app_name = "eventos"
urlpatterns = [
    path("", views.EventoListView.as_view(), name="lista"),
    path("eventos/<int:pk>/", views.EventoDetailView.as_view(), name="detalhe"),
]
