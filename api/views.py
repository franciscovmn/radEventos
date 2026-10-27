from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
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


@extend_schema(
    request=AuthTokenSerializer,
    responses={200: {"type": "object", "properties": {"token": {"type": "string"}}}},
    description="Autentica com usuário e senha e retorna um token de acesso.",
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
            queryset = Atividade.objects.com_vagas()
            termo = self.request.query_params.get("search", "").strip()
            if termo:
                queryset = queryset.filter(
                    Q(titulo__icontains=termo) | Q(descricao__icontains=termo)
                )
            ordenacao = self.request.query_params.get("ordering", "inicio")
            if ordenacao not in {"inicio", "-inicio"}:
                ordenacao = "inicio"
            return queryset.order_by(ordenacao, "pk")
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


@extend_schema(
    parameters=[OpenApiParameter("evento_id", int, OpenApiParameter.PATH)],
    description="Retorna os dados públicos de um evento e suas atividades em ordem cronológica.",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def programacao_evento(request, evento_id):
    evento = get_object_or_404(Evento.objects.select_related("organizador"), pk=evento_id)
    atividades = Atividade.objects.com_vagas().filter(evento=evento).order_by("inicio", "pk")
    return Response({
        "evento": EventoSerializer(evento).data,
        "atividades": AtividadeSerializer(atividades, many=True).data,
    })


@extend_schema(
    description="Lista as atividades dos eventos em que o participante autenticado está inscrito, em ordem cronológica.",
    responses={200: AtividadeSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def agenda_participante(request):
    atividades = Atividade.objects.com_vagas().filter(
        inscricoes__inscricao_evento__participante=request.user
    ).distinct().order_by("inicio", "pk")
    return Response(AtividadeSerializer(atividades, many=True).data)
