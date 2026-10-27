from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from inscricoes.models import Atividade, Evento, Sala

from .permissions import OrganizaEventos, OrganizadorDoEvento
from .serializers import AtividadeSerializer, EventoSerializer, SalaSerializer


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
