from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views


app_name = "api"
router = DefaultRouter()
urlpatterns = [path("token/", views.obter_token, name="token")] + router.urls
