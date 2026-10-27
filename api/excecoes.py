from django.core.exceptions import ValidationError as ErroDeValidacao
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler


def tratar_excecao(exc, context):
    if isinstance(exc, ErroDeValidacao):
        exc = ValidationError(detail=as_serializer_error(exc))
    return exception_handler(exc, context)
