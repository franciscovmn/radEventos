from django.contrib import admin
from django.urls import include, path

from inscricoes.views import CadastroView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("contas/cadastro/", CadastroView.as_view(), name="cadastro"),
    path("contas/", include("django.contrib.auth.urls")),
    path("api/", include("api.urls")),
    path("", include("inscricoes.urls")),
]
