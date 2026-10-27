from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from inscricoes import servicos
from inscricoes.models import Atividade, Evento, InscricaoAtividade, InscricaoEvento, Sala

from .permissions import OrganizaEventos, OrganizadorDoEvento
from .serializers import (
    AtividadeSerializer, EventoSerializer, InscricaoAtividadeSerializer,
    InscricaoEventoSerializer, SalaSerializer,
)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def obter_token(request):
    serializer = AuthTokenSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    token, _ = Token.objects.get_or_create(user=serializer.validated_data["user"])
    return Response({"token": token.key})


class SalaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Sala.objects.all()
    serializer_class = SalaSerializer
    permission_classes = [AllowAny]


class ViewSetDoOrganizador(viewsets.ModelViewSet):
    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [IsAuthenticated(), OrganizaEventos(), OrganizadorDoEvento()]


class EventoViewSet(ViewSetDoOrganizador):
    queryset = Evento.objects.select_related("organizador")
    serializer_class = EventoSerializer

    def perform_create(self, serializer):
        serializer.save(organizador=self.request.user)


class AtividadeViewSet(ViewSetDoOrganizador):
    serializer_class = AtividadeSerializer

    def get_queryset(self):
        if self.action in ("list", "retrieve"):
            return Atividade.objects.com_vagas()
        return Atividade.objects.select_related("evento", "sala")

    def perform_create(self, serializer):
        self.check_object_permissions(self.request, serializer.validated_data["evento"])
        serializer.save()


class InscricaoViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    lookup_value_regex = "[0-9]+"


class InscricaoEventoViewSet(InscricaoViewSet):
    serializer_class = InscricaoEventoSerializer

    def get_queryset(self):
        return InscricaoEvento.objects.filter(
            participante=self.request.user
        ).select_related("evento", "participante")

    def destroy(self, request, pk):
        servicos.cancelar_inscricao_no_evento(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InscricaoAtividadeViewSet(InscricaoViewSet):
    serializer_class = InscricaoAtividadeSerializer

    def get_queryset(self):
        return InscricaoAtividade.objects.filter(
            inscricao_evento__participante=self.request.user
        ).select_related("atividade", "inscricao_evento")

    def destroy(self, request, pk):
        servicos.cancelar_inscricao_em_atividade(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
