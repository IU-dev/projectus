import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower, Round
from .permissions import ProjectPermission, SystemPermission
class UserManager(BaseUserManager):
    use_in_migrations = True
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=email.strip().lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("email_verified", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superuser must have is_staff and is_superuser")
        return self.create_user(email, password, **extra_fields)
class User(AbstractUser):
    username = None
    email = models.EmailField("Email", unique=True)
    email_verified = models.BooleanField(default=False)
    verification_nonce = models.UUIDField(default=uuid.uuid4, editable=False)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()
    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="unique_user_email_ci")]
    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
    def __str__(self):
        return self.email
class ProjectRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "На рассмотрении"
        APPROVED = "approved", "Одобрена"
        REJECTED = "rejected", "Отклонена"
    applicant = models.ForeignKey(User, on_delete=models.PROTECT, related_name="project_requests")
    title = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name="decisions")
    decision_note = models.TextField(blank=True)
    class Meta:
        ordering = ["-created_at"]
class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_projects")
    request = models.OneToOneField(ProjectRequest, on_delete=models.PROTECT, related_name="project")
    title = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    goals = models.JSONField("Цели проекта", default=list, blank=True)
    tasks = models.JSONField("Задачи проекта", default=list, blank=True)
    start_date = models.DateField("Начальная дата", null=True, blank=True)
    end_date = models.DateField("Конечная дата", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    require_payment_bank_details = models.BooleanField("Требовать банковские реквизиты", default=True)
    payment_sequence = models.PositiveIntegerField(default=0, editable=False)
    class Meta:
        ordering = ["-created_at"]
class ProjectIndicator(models.Model):
    class Kind(models.TextChoices):
        QUALITATIVE = "qualitative", "Качественный"
        QUANTITATIVE = "quantitative", "Количественный"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="indicators")
    title = models.CharField("Показатель", max_length=1000)
    kind = models.CharField("Тип показателя", max_length=20, choices=Kind.choices)
    target_value = models.DecimalField("Целевое значение", max_digits=15, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(Decimal("0.001"))])
    unit = models.CharField("Единица измерения", max_length=50, blank=True)
    current_value = models.DecimalField(max_digits=15, decimal_places=3, default=0, editable=False)
    result = models.TextField("Текущий результат", blank=True)
    achieved = models.BooleanField("Достигнут", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(current_value__gte=0), name="indicator_nonnegative_current"),
            models.CheckConstraint(condition=(
                models.Q(kind="quantitative", target_value__isnull=False, target_value__gt=0, result="", achieved=False)
                | models.Q(kind="qualitative", target_value__isnull=True, current_value=0, unit="")
            ), name="indicator_kind_values"),
        ]

    @property
    def progress_percent(self):
        if self.kind == self.Kind.QUANTITATIVE and self.target_value:
            return round(self.current_value / self.target_value * 100, 1)
        return None


class ProjectEvent(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Запланировано"
        CONDUCTED = "conducted", "Проведено · ожидает подтверждения"
        CONFIRMED = "confirmed", "Подтверждено"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="project_events")
    title = models.CharField("Название мероприятия", max_length=200)
    start_date = models.DateField("Плановая дата начала")
    end_date = models.DateField("Плановая дата окончания")
    expected_result = models.TextField("Ожидаемый результат")
    tasks = models.JSONField("Задачи проекта", default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    actual_start_date = models.DateField("Фактическая дата начала", null=True, blank=True)
    actual_end_date = models.DateField("Фактическая дата окончания", null=True, blank=True)
    actual_result = models.TextField("Фактический результат", blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_events")
    confirmed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="confirmed_events")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="event_plan_dates_order"),
            models.CheckConstraint(condition=models.Q(actual_end_date__isnull=True) | models.Q(actual_end_date__gte=models.F("actual_start_date")), name="event_actual_dates_order"),
            models.CheckConstraint(condition=(models.Q(status="planned") | (models.Q(status__in=["conducted", "confirmed"], actual_start_date__isnull=False, actual_end_date__isnull=False) & ~models.Q(actual_result=""))), name="event_result_required"),
            models.CheckConstraint(condition=(models.Q(status="confirmed", confirmed_at__isnull=False, confirmed_by__isnull=False) | models.Q(status__in=["planned", "conducted"], confirmed_at__isnull=True, confirmed_by__isnull=True)), name="event_confirmation_metadata"),
        ]


class EventIndicator(models.Model):
    event = models.ForeignKey(ProjectEvent, on_delete=models.CASCADE, related_name="indicator_links")
    indicator = models.ForeignKey(ProjectIndicator, on_delete=models.PROTECT, related_name="event_links")
    planned_value = models.DecimalField(max_digits=15, decimal_places=3, null=True, blank=True)
    actual_value = models.DecimalField(max_digits=15, decimal_places=3, null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(fields=["event", "indicator"], name="unique_event_indicator"),
            models.CheckConstraint(condition=models.Q(planned_value__isnull=True) | models.Q(planned_value__gte=0), name="event_indicator_plan_nonnegative"),
            models.CheckConstraint(condition=models.Q(actual_value__isnull=True) | models.Q(actual_value__gte=0), name="event_indicator_actual_nonnegative"),
        ]


def event_attachment_path(instance, filename):
    return f"events/{instance.event_id}/{uuid.uuid4().hex}"


class EventAttachment(models.Model):
    class Kind(models.TextChoices):
        OTHER = "other", "Другое"
        PHOTOS = "photos", "Фотографии"
        PARTICIPANTS = "participants", "Списки участников"
        ORGANIZATIONAL = "organizational", "Организационные документы"
        ORDERS = "orders", "Приказы"
        PROGRAM = "program", "Программа мероприятия"
        REPORT = "report", "Отчёты и отзывы"

    event = models.ForeignKey(ProjectEvent, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=event_attachment_path)
    original_name = models.CharField(max_length=255)
    kind = models.CharField(max_length=30, choices=Kind.choices, default=Kind.OTHER)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]


class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="unique_project_member")]
class ProjectMemberPermissions(models.Model):
    membership = models.ForeignKey(ProjectMember, on_delete=models.CASCADE, related_name="grants")
    code = models.CharField(max_length=40, choices=ProjectPermission.choices)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "code"], name="unique_project_grant")]
class SystemPermissions(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="system_grants")
    code = models.CharField(max_length=40, choices=SystemPermission.choices)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "code"], name="unique_system_grant")]
class ProjectMemberInvitations(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    permissions = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
class AuditEvent(models.Model):
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=200)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
class RateLimit(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()


class BudgetTemplate(models.Model):
    name = models.CharField("Название", max_length=200)
    active = models.BooleanField("Активен", default=True)

    def __str__(self):
        return self.name


class BudgetTemplateItem(models.Model):
    template = models.ForeignKey(BudgetTemplate, on_delete=models.CASCADE, related_name="items")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children", verbose_name="Крупная статья")
    name = models.CharField("Название", max_length=200)
    explanation = models.TextField("Пояснение", blank=True)
    position = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["position", "pk"]

    def clean(self):
        if self.parent_id and (self.parent_id == self.pk or self.parent.parent_id or self.parent.template_id != self.template_id):
            raise ValidationError({"parent": "Выберите крупную статью этого шаблона. Допускаются только два уровня."})
        if self.pk and self.parent_id and self.children.exists():
            raise ValidationError({"parent": "Статья с подстатьями должна оставаться крупной статьёй."})

    def __str__(self):
        return self.name


class ProjectPaymentApprover(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="payment_approvers")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="unique_project_payment_approver")]


class BudgetRevision(models.Model):
    class Kind(models.TextChoices):
        INITIAL = "initial", "Исходная смета"
        AMENDMENT = "amendment", "Изменение сметы"
        TRANSFER = "transfer", "Перенос средств"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PENDING = "pending", "На согласовании"
        ACTIVE = "active", "Действующая"
        REJECTED = "rejected", "Отклонена"
        SUPERSEDED = "superseded", "Заменена"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="budget_revisions")
    number = models.PositiveIntegerField()
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INITIAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    base = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True)
    reason = models.TextField("Причина изменения", blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="budget_revisions")
    decided_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="budget_decisions")
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["project", "number"], name="unique_budget_revision_number"),
            models.UniqueConstraint(fields=["project"], condition=models.Q(status="active"), name="one_active_budget"),
            models.UniqueConstraint(fields=["project"], condition=models.Q(status__in=["draft", "pending"]), name="one_open_budget"),
            models.CheckConstraint(condition=models.Q(kind="initial") | ~models.Q(reason=""), name="budget_change_reason"),
        ]


class BudgetSection(models.Model):
    revision = models.ForeignKey(BudgetRevision, on_delete=models.CASCADE, related_name="sections")
    key = models.UUIDField(default=uuid.uuid4, editable=False)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children", verbose_name="Крупная статья")
    name = models.CharField("Название", max_length=200)
    explanation = models.TextField("Пояснение", blank=True)
    position = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [models.UniqueConstraint(fields=["revision", "key"], name="unique_budget_section_key")]

    def clean(self):
        if self.parent_id:
            if self.parent_id == self.pk or self.parent.revision_id != self.revision_id or self.parent.parent_id:
                raise ValidationError({"parent": "Выберите крупную статью этой версии сметы."})
            if self.parent.lines.exists():
                raise ValidationError({"parent": "В крупной статье уже есть строки. Сначала перенесите их в другую статью."})
        if self.pk and self.parent_id and self.children.exists():
            raise ValidationError({"parent": "Статья с подстатьями должна оставаться крупной статьёй."})

    def __str__(self):
        return self.name


class BudgetLine(models.Model):
    revision = models.ForeignKey(BudgetRevision, on_delete=models.CASCADE, related_name="lines")
    key = models.UUIDField(default=uuid.uuid4, editable=False)
    section = models.ForeignKey(BudgetSection, on_delete=models.PROTECT, related_name="lines", verbose_name="Статья / подстатья")
    name = models.CharField("Наименование расхода", max_length=500)
    unit_price = models.DecimalField("Цена единицы", max_digits=18, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0.01"))])
    quantity = models.DecimalField("Количество", max_digits=15, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(Decimal("0.001"))])
    unit_name = models.CharField("Единица измерения", max_length=50, blank=True)
    total_amount = models.DecimalField("Общая стоимость", max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    cofinancing_amount = models.DecimalField("Софинансирование", max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    requested_amount = models.DecimalField("Запрашиваемая сумма", max_digits=18, decimal_places=2, validators=[MinValueValidator(0)])
    comment = models.TextField("Комментарий", blank=True)
    position = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["revision", "key"], name="unique_budget_line_key"),
            models.CheckConstraint(condition=models.Q(total_amount__gt=0, cofinancing_amount__gte=0, requested_amount__gte=0), name="budget_line_amounts_positive"),
            models.CheckConstraint(condition=models.Q(total_amount=Round(models.F("cofinancing_amount") + models.F("requested_amount"), 2)), name="budget_line_amounts_sum"),
            models.CheckConstraint(condition=models.Q(unit_price__isnull=True, quantity__isnull=True) | (models.Q(unit_price__isnull=False, quantity__isnull=False, unit_price__gt=0, quantity__gt=0) & ~models.Q(unit_name="")), name="budget_line_unit_pair"),
        ]

    def clean(self):
        errors = {}
        if self.section_id and (self.section.revision_id != self.revision_id or self.section.children.exists()):
            errors["section"] = "Выберите статью этой версии без подстатей."
        if (self.unit_price is None) != (self.quantity is None):
            errors["quantity"] = "Цена и количество заполняются вместе."
        if self.quantity is not None and not self.unit_name.strip():
            errors["unit_name"] = "Укажите единицу измерения."
        if self.unit_price is not None and self.quantity is not None and self.total_amount is not None:
            if (self.unit_price * self.quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != self.total_amount:
                errors["total_amount"] = "Общая стоимость должна равняться цене, умноженной на количество с округлением до копеек."
        if all(value is not None for value in [self.total_amount, self.cofinancing_amount, self.requested_amount]):
            if self.total_amount != self.cofinancing_amount + self.requested_amount:
                errors["total_amount"] = "Общая стоимость должна равняться сумме софинансирования и запрашиваемых средств."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class FundReceipt(models.Model):
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="fund_receipts")
    amount = models.DecimalField("Сумма, ₽", max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    received_date = models.DateField("Дата поступления")
    comment = models.TextField("Назначение / комментарий")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_date", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="receipt_positive")]


class PaymentOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PENDING = "pending", "На согласовании"
        APPROVED = "approved", "Согласован"
        REJECTED = "rejected", "Отклонён"
        EXECUTED = "executed", "Исполнен"

    class RecipientType(models.TextChoices):
        FL = "fl", "Физическое лицо"
        IP = "ip", "Индивидуальный предприниматель"
        ORG = "org", "Юридическое лицо"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="payment_orders")
    number = models.PositiveIntegerField()
    budget_line_key = models.UUIDField()
    line_name = models.CharField(max_length=500)
    section_path = models.CharField(max_length=500)
    amount = models.DecimalField("Сумма, ₽", max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    description = models.TextField("Основание заявки")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="payment_orders")
    bank_details_required = models.BooleanField(default=True)
    recipient_type = models.CharField("Тип получателя", max_length=10, choices=RecipientType.choices)
    recipient_name = models.CharField("Полное имя / наименование получателя", max_length=500)
    inn = models.CharField("ИНН", max_length=30)
    kpp = models.CharField("КПП", max_length=30, blank=True)
    account = models.CharField("Расчётный счёт", max_length=40, blank=True)
    bank_name = models.CharField("Банк", max_length=300, blank=True)
    bik = models.CharField("БИК", max_length=30, blank=True)
    correspondent_account = models.CharField("Корреспондентский счёт", max_length=40, blank=True)
    events = models.ManyToManyField(ProjectEvent, blank=True, related_name="payments")
    payment_document_date = models.DateField("Дата платежного документа", null=True, blank=True)
    payment_document_number = models.CharField("Номер платежного документа", max_length=100, blank=True)
    payment_purpose = models.TextField("Назначение платежа", blank=True)
    executed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="executed_payments")
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["project", "number"], name="unique_payment_number"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_positive"),
            models.CheckConstraint(condition=~models.Q(status="executed") | (models.Q(payment_document_date__isnull=False, executed_at__isnull=False, executed_by__isnull=False) & ~models.Q(payment_document_number="") & ~models.Q(payment_purpose="")), name="payment_execution_required"),
        ]


class PaymentApproval(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает решения"
        APPROVED = "approved", "Одобрено"
        REJECTED = "rejected", "Отклонено"

    payment = models.ForeignKey(PaymentOrder, on_delete=models.CASCADE, related_name="approvals")
    approver = models.ForeignKey(User, on_delete=models.PROTECT)
    position = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    comment = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [models.UniqueConstraint(fields=["payment", "approver"], name="unique_payment_approval")]


def payment_attachment_path(instance, filename):
    return f"payments/{instance.payment_id}/{uuid.uuid4().hex}"


class PaymentAttachment(models.Model):
    payment = models.ForeignKey(PaymentOrder, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=payment_attachment_path)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
