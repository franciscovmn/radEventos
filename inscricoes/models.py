from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Count, F, Q
from django.urls import reverse
from django.utils import timezone


class ModeloValidado(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self.full_clean()
            return super().save(*args, **kwargs)


class Sala(ModeloValidado):
    nome = models.CharField("Nome", max_length=100, unique=True)
    bloco = models.CharField("Bloco", max_length=60)
    capacidade = models.PositiveIntegerField("Capacidade", validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.CheckConstraint(condition=Q(capacidade__gte=1), name="sala_capacidade_positiva")
        ]

    def __str__(self):
        return f"{self.nome} - {self.bloco}"

    def clean(self):
        super().clean()
        if self.pk and self.capacidade is not None:
            if self.atividades.annotate(total=Count("inscricoes")).filter(
                total__gt=self.capacidade
            ).exists():
                raise ValidationError({"capacidade": "Há atividades com mais inscritos que essa capacidade."})


class Evento(ModeloValidado):
    nome = models.CharField("Nome", max_length=150)
    descricao = models.TextField("Descrição")
    data_inicio = models.DateField("Data de início")
    data_fim = models.DateField("Data de fim")
    inscricoes_abertas = models.BooleanField("Inscrições abertas", default=True)
    organizador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="eventos_organizados",
        verbose_name="Organizador",
    )

    class Meta:
        ordering = ["data_inicio", "nome"]
        permissions = [("organizar_eventos", "Pode organizar eventos e atividades")]
        constraints = [
            models.CheckConstraint(condition=Q(data_fim__gte=F("data_inicio")), name="evento_periodo_valido")
        ]

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return reverse("eventos:detalhe", args=[self.pk])

    def pode_ser_gerenciado_por(self, usuario):
        return (
            usuario.is_authenticated
            and usuario.has_perm("inscricoes.organizar_eventos")
            and self.organizador_id == usuario.pk
        )

    def clean(self):
        super().clean()
        if not self.data_inicio or not self.data_fim:
            return
        if self.data_fim < self.data_inicio:
            raise ValidationError({"data_fim": "A data de fim não pode vir antes do início."})
        if self.pk and self.atividades.filter(
            Q(inicio__date__lt=self.data_inicio) | Q(fim__date__gt=self.data_fim)
        ).exists():
            raise ValidationError("O novo período deixaria atividades fora do evento.")


class AtividadeQuerySet(models.QuerySet):
    def sobrepostas(self, inicio, fim):
        return self.filter(inicio__lt=fim, fim__gt=inicio)

    def com_vagas(self):
        return self.select_related("evento", "sala").annotate(
            total_inscritos=Count("inscricoes"),
            vagas_restantes=F("sala__capacidade") - Count("inscricoes"),
        ).order_by("inicio", "pk")


class Atividade(ModeloValidado):
    class Tipo(models.TextChoices):
        PALESTRA = "PA", "Palestra"
        TREINAMENTO = "TR", "Treinamento"
        APRESENTACAO = "AP", "Apresentação"

    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="atividades", verbose_name="Evento")
    titulo = models.CharField("Título", max_length=150)
    tipo = models.CharField("Tipo", max_length=2, choices=Tipo.choices)
    descricao = models.TextField("Descrição")
    responsavel = models.CharField("Responsável", max_length=120)
    sala = models.ForeignKey(Sala, on_delete=models.PROTECT, related_name="atividades", verbose_name="Sala")
    inicio = models.DateTimeField("Início")
    fim = models.DateTimeField("Fim")
    objects = AtividadeQuerySet.as_manager()

    class Meta:
        ordering = ["inicio", "titulo"]
        constraints = [
            models.CheckConstraint(condition=Q(fim__gt=F("inicio")), name="atividade_intervalo_valido")
        ]

    def __str__(self):
        return self.titulo

    def clean(self):
        super().clean()
        if not self.inicio or not self.fim:
            return
        if self.fim <= self.inicio:
            raise ValidationError({"fim": "O fim precisa ser depois do início."})
        if self.evento_id:
            if (
                timezone.localtime(self.inicio).date() < self.evento.data_inicio
                or timezone.localtime(self.fim).date() > self.evento.data_fim
            ):
                raise ValidationError("A atividade precisa acontecer dentro do período do evento.")
            if self.pk:
                original = Atividade.objects.get(pk=self.pk)
                if original.evento_id != self.evento_id and self.inscricoes.exists():
                    raise ValidationError("Uma atividade com inscritos não pode mudar de evento.")
        if self.sala_id:
            if Atividade.objects.sobrepostas(self.inicio, self.fim).filter(
                sala_id=self.sala_id
            ).exclude(pk=self.pk).exists():
                raise ValidationError({"sala": "A sala já está ocupada nesse horário."})
            if self.pk and self.inscricoes.count() > self.sala.capacidade:
                raise ValidationError({"sala": "Esta sala não comporta os inscritos da atividade."})
        if self.pk:
            participantes = self.inscricoes.values("inscricao_evento__participante_id")
            if InscricaoAtividade.objects.filter(
                inscricao_evento__participante_id__in=participantes,
                atividade__inicio__lt=self.fim,
                atividade__fim__gt=self.inicio,
            ).exclude(atividade_id=self.pk).exists():
                raise ValidationError("O novo horário conflita com a agenda de um participante inscrito.")


class InscricaoEvento(ModeloValidado):
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="inscricoes", verbose_name="Evento")
    participante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inscricoes_eventos",
        verbose_name="Participante",
    )
    data = models.DateTimeField("Data de inscrição", auto_now_add=True)

    class Meta:
        verbose_name = "Inscrição no evento"
        verbose_name_plural = "Inscrições nos eventos"
        ordering = ["data", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["evento", "participante"], name="inscricao_evento_unica")
        ]

    def __str__(self):
        return f"{self.participante} - {self.evento}"

    def clean(self):
        super().clean()
        if self.evento_id and self._state.adding and not self.evento.inscricoes_abertas:
            raise ValidationError("As inscrições deste evento estão fechadas.")
        if self.evento_id and self.participante_id:
            if InscricaoEvento.objects.filter(
                evento_id=self.evento_id, participante_id=self.participante_id
            ).exclude(pk=self.pk).exists():
                raise ValidationError("Este participante já está inscrito no evento.")
        if self.pk:
            original = InscricaoEvento.objects.get(pk=self.pk)
            if original.evento_id != self.evento_id or original.participante_id != self.participante_id:
                raise ValidationError("O evento e o participante de uma inscrição não podem ser trocados.")


class InscricaoAtividade(ModeloValidado):
    inscricao_evento = models.ForeignKey(
        InscricaoEvento,
        on_delete=models.CASCADE,
        related_name="inscricoes_atividades",
        verbose_name="Inscrição no evento",
    )
    atividade = models.ForeignKey(Atividade, on_delete=models.CASCADE, related_name="inscricoes", verbose_name="Atividade")
    data = models.DateTimeField("Data de inscrição", auto_now_add=True)

    class Meta:
        verbose_name = "Inscrição em atividade"
        verbose_name_plural = "Inscrições em atividades"
        ordering = ["atividade__inicio", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["inscricao_evento", "atividade"], name="inscricao_atividade_unica")
        ]

    def __str__(self):
        return f"{self.inscricao_evento.participante} - {self.atividade}"

    def clean(self):
        super().clean()
        if not self.inscricao_evento_id or not self.atividade_id:
            return
        atividade = self.atividade
        if self.inscricao_evento.evento_id != atividade.evento_id:
            raise ValidationError("A inscrição precisa ser do mesmo evento da atividade.")
        if atividade.inscricoes.exclude(pk=self.pk).count() >= atividade.sala.capacidade:
            raise ValidationError("Esta atividade está lotada.")
        if InscricaoAtividade.objects.filter(
            inscricao_evento__participante_id=self.inscricao_evento.participante_id,
            atividade__inicio__lt=atividade.fim,
            atividade__fim__gt=atividade.inicio,
        ).exclude(pk=self.pk).exists():
            raise ValidationError("Esta atividade conflita com outra inscrição na sua agenda.")
