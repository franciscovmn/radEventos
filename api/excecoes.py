from django.core.exceptions import NON_FIELD_ERRORS
from django.core.exceptions import ValidationError as ErroDeValidacao
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import as_serializer_error
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler


def tratar_excecao(exc, context):
    if isinstance(exc, ErroDeValidacao):
        detalhe = as_serializer_error(exc)
        if NON_FIELD_ERRORS in detalhe:
            detalhe[api_settings.NON_FIELD_ERRORS_KEY] = detalhe.pop(NON_FIELD_ERRORS)
        exc = ValidationError(detail=detalhe)
    return exception_handler(exc, context)
