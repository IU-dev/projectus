"""Financial transitions serialize on the project row (PostgreSQL).

Every writer takes this lock before reading state, including editors and files.
Pending requests never reserve funds. All money remains Decimal throughout.
"""
from decimal import Decimal
from pathlib import Path
import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import (Project, BudgetRevision, BudgetSection, BudgetLine, BudgetTemplate,
                     ProjectPaymentApprover, PaymentApproval, PaymentAttachment)
from .permissions import ProjectPermission as PP, has_project_permission
from .services import record

ZERO = Decimal("0.00")
FINANCE_PERMISSIONS = (PP.VIEW_FINANCE, PP.EDIT_BUDGET, PP.PREPARE_PAYMENTS,
                       PP.APPROVE_PAYMENTS, PP.APPROVE_BUDGET_CHANGES,
                       PP.EXECUTE_PAYMENTS, PP.RECORD_RECEIPTS)


def require_permission(actor, project, code):
    if not has_project_permission(actor, project, code):
        raise PermissionDenied


def lock_project(project):
    return Project.objects.select_for_update().get(pk=project.pk)


def active_revision(project):
    return project.budget_revisions.select_related('created_by', 'decided_by').filter(status="active").first()


@transaction.atomic
def ensure_initial(project, actor):
    project = lock_project(project)
    if not any(has_project_permission(actor, project, code) for code in FINANCE_PERMISSIONS):
        raise PermissionDenied
    revision = project.budget_revisions.order_by("number").first()
    if revision is None:
        revision = BudgetRevision.objects.create(project=project, number=1, created_by=actor)
        record(actor, "budget.revision_created", revision.pk, project=str(project.pk), kind="initial")
    return revision


def editable_revision(project, revision_id):
    revision = get_object_or_404(project.budget_revisions, pk=revision_id)
    if revision.status != "draft":
        raise PermissionDenied("Изменять можно только черновик сметы.")
    return revision


def sum_amount(query, field="amount"):
    return (query.aggregate(value=Sum(field))["value"] or ZERO).quantize(Decimal('0.01'))


def balances(project):
    received = sum_amount(project.fund_receipts.all())
    grouped = {row["status"]: row["amount"].quantize(Decimal('0.01')) for row in project.payment_orders.filter(
        status__in=["approved", "executed"]).values("status").annotate(amount=Sum("amount"))}
    reserved, executed = grouped.get("approved", ZERO), grouped.get("executed", ZERO)
    return {"received": received, "reserved": reserved, "executed": executed,
            "account_balance": received - executed, "available": received - executed - reserved}


def commitments(project):
    return {row["budget_line_key"]: row["amount"].quantize(Decimal('0.01')) for row in project.payment_orders.filter(
        status__in=["approved", "executed"]).values("budget_line_key").annotate(amount=Sum("amount"))}


def validate_revision(revision):
    sections = list(revision.sections.select_related("parent"))
    lines = list(revision.lines.select_related("section"))
    for section in sections:
        section.full_clean()
    for line in lines:
        line.full_clean()
    if not lines:
        raise ValidationError("Добавьте хотя бы одну строку сметы.")
    planned = {line.key: line.total_amount for line in lines}
    for key, amount in commitments(revision.project).items():
        if planned.get(key, ZERO) < amount:
            raise ValidationError("Лимит строки нельзя снизить ниже согласованных и исполненных платежей; такую строку нельзя удалить.")
    if revision.kind != "initial":
        if not revision.reason.strip():
            raise ValidationError("Укажите причину изменения.")
        current = active_revision(revision.project)
        if current is None or revision.base_id != current.pk:
            raise ValidationError("Основание изменения больше не является действующей сметой.")
    if revision.kind == "transfer":
        before = dict(revision.base.lines.values_list("key", "total_amount"))
        deltas = [planned.get(key, ZERO) - before.get(key, ZERO) for key in planned.keys() | before.keys()]
        if sum(deltas, ZERO) != ZERO or not any(d > 0 for d in deltas) or not any(d < 0 for d in deltas):
            raise ValidationError("Перенос должен сохранять общую стоимость проекта и содержать уменьшение и увеличение лимитов строк.")


@transaction.atomic
def apply_template(actor, project, revision_id, template_id):
    project = lock_project(project)
    require_permission(actor, project, PP.EDIT_BUDGET)
    revision = editable_revision(project, revision_id)
    if revision.kind != "initial" or revision.sections.exists() or revision.lines.exists():
        raise ValidationError("Шаблон можно применить только к пустой исходной смете.")
    template = get_object_or_404(BudgetTemplate, pk=template_id, active=True)
    items = list(template.items.select_related("parent"))
    for item in items:
        item.full_clean()
    mapping = {}
    for item in sorted(items, key=lambda item: bool(item.parent_id)):
        mapping[item.pk] = BudgetSection.objects.create(revision=revision, name=item.name,
            explanation=item.explanation, position=item.position, parent=mapping.get(item.parent_id))
    record(actor, "budget.template_applied", revision.pk, project=str(project.pk), template=template.pk)


@transaction.atomic
def clone_revision(actor, project, kind, reason):
    project = lock_project(project)
    require_permission(actor, project, PP.EDIT_BUDGET)
    if kind not in ["amendment", "transfer"] or not reason.strip():
        raise ValidationError("Выберите изменение или перенос и укажите причину.")
    base = active_revision(project)
    if base is None:
        raise ValidationError("Сначала опубликуйте исходную смету.")
    if project.budget_revisions.filter(status__in=["draft", "pending"]).exists():
        raise ValidationError("В проекте уже есть черновик или изменение на согласовании.")
    number = project.budget_revisions.aggregate(value=Max("number"))["value"] + 1
    revision = BudgetRevision.objects.create(project=project, number=number, kind=kind, reason=reason.strip(), base=base, created_by=actor)
    mapping = {}
    for section in sorted(base.sections.all(), key=lambda section: bool(section.parent_id)):
        mapping[section.pk] = BudgetSection.objects.create(revision=revision, key=section.key,
            name=section.name, explanation=section.explanation, position=section.position, parent=mapping.get(section.parent_id))
    BudgetLine.objects.bulk_create([BudgetLine(revision=revision, key=line.key, section=mapping[line.section_id],
        **{name: getattr(line, name) for name in ["name", "unit_price", "quantity", "unit_name", "total_amount", "cofinancing_amount", "requested_amount", "comment", "position"]}) for line in base.lines.all()])
    record(actor, "budget.revision_created", revision.pk, project=str(project.pk), kind=kind, base=base.pk)
    return revision


@transaction.atomic
def publish_initial(actor, project, revision_id):
    project = lock_project(project)
    require_permission(actor, project, PP.EDIT_BUDGET)
    revision = editable_revision(project, revision_id)
    if revision.kind != "initial" or active_revision(project):
        raise ValidationError("Можно публиковать только исходную смету.")
    validate_revision(revision)
    revision.status = "active"
    revision.decided_by = actor
    revision.decided_at = timezone.now()
    revision.save()
    record(actor, "budget.initial_published", revision.pk, project=str(project.pk))


@transaction.atomic
def submit_revision(actor, project, revision_id):
    project = lock_project(project)
    require_permission(actor, project, PP.EDIT_BUDGET)
    revision = editable_revision(project, revision_id)
    if revision.kind == "initial":
        raise ValidationError("Исходную смету нужно опубликовать.")
    validate_revision(revision)
    revision.status = "pending"
    revision.submitted_at = timezone.now()
    revision.save()
    record(actor, "budget.revision_submitted", revision.pk, project=str(project.pk))


@transaction.atomic
def decide_revision(actor, project, revision_id, approve):
    project = lock_project(project)
    require_permission(actor, project, PP.APPROVE_BUDGET_CHANGES)
    revision = get_object_or_404(project.budget_revisions, pk=revision_id)
    if revision.status != "pending":
        raise ValidationError("Изменение уже рассмотрено или ещё не отправлено.")
    if approve:
        validate_revision(revision)
        project.budget_revisions.filter(status="active").update(status="superseded")
    revision.status = "active" if approve else "rejected"
    revision.decided_by = actor
    revision.decided_at = timezone.now()
    revision.save()
    record(actor, "budget.revision_approved" if approve else "budget.revision_rejected", revision.pk, project=str(project.pk))


def validate_recipient(payment, required):
    errors = {}
    if payment.recipient_type not in ["fl", "ip", "org"]:
        errors["recipient_type"] = "Выберите тип получателя."
    if not payment.recipient_name.strip():
        errors["recipient_name"] = "Укажите получателя."
    lengths = {"inn": 10 if payment.recipient_type == "org" else 12, "kpp": 9,
               "account": 20, "bik": 9, "correspondent_account": 20}
    for field, length in lengths.items():
        value = re.sub(r"\s+", "", getattr(payment, field))
        setattr(payment, field, value)
        mandatory = field == "inn" or (field == "kpp" and payment.recipient_type == "org") or (required and field in ["account", "bik", "correspondent_account"])
        if (value or mandatory) and not re.fullmatch(r"[0-9]{%d}" % length, value):
            errors[field] = f"Укажите {length} цифр."
    if payment.recipient_type in ["fl", "ip"] and payment.kpp:
        errors["kpp"] = "Для физического лица и ИП КПП должен быть пустым."
    if required and not payment.bank_name.strip():
        errors["bank_name"] = "Укажите банк получателя."
    if errors:
        raise ValidationError(errors)


def approver_candidates(project):
    users = {project.owner_id: project.owner}
    for member in project.memberships.select_related("user"):
        if member.user.is_active and member.user.email_verified:
            users[member.user_id] = member.user
    return users


def eligible_approver_ids(project):
    eligible = set(project.memberships.filter(grants__code=PP.APPROVE_PAYMENTS,
        user__is_active=True, user__email_verified=True).values_list('user_id', flat=True))
    if project.owner.is_active and project.owner.email_verified:
        eligible.add(project.owner_id)
    return eligible


def validate_approvers(project, users):
    eligible = eligible_approver_ids(project)
    for user in users:
        if user.pk not in eligible:
            raise ValidationError("Каждый согласующий должен быть действующим участником или владельцем и иметь право согласовывать платежи.")


@transaction.atomic
def save_settings(actor, project, users, required):
    project = lock_project(project)
    require_permission(actor, project, PP.EDIT_BUDGET)
    validate_approvers(project, users)
    project.require_payment_bank_details = required
    project.save(update_fields=["require_payment_bank_details"])
    project.payment_approvers.all().delete()
    ProjectPaymentApprover.objects.bulk_create([ProjectPaymentApprover(project=project, user=user, position=i) for i, user in enumerate(users)])
    record(actor, "budget.settings_updated", project.pk, approver_count=len(users), bank_details_required=required)


def check_capacity(project, payment, exclude_self=False):
    revision = active_revision(project)
    line = revision.lines.filter(key=payment.budget_line_key).first() if revision else None
    if line is None:
        raise ValidationError("В действующей смете больше нет выбранной строки.")
    payments = project.payment_orders.filter(status__in=["approved", "executed"])
    if exclude_self:
        payments = payments.exclude(pk=payment.pk)
    if sum_amount(project.fund_receipts.all()) - sum_amount(payments) < payment.amount:
        raise ValidationError("Недостаточно доступных средств с учётом согласованных платежей.")
    if line.total_amount - sum_amount(payments.filter(budget_line_key=payment.budget_line_key)) < payment.amount:
        raise ValidationError("Недостаточно остатка по строке сметы.")


@transaction.atomic
def submit_payment(actor, project, payment_id):
    project = lock_project(project)
    require_permission(actor, project, PP.PREPARE_PAYMENTS)
    payment = get_object_or_404(project.payment_orders, pk=payment_id)
    if payment.created_by_id != actor.pk or payment.status != "draft":
        raise PermissionDenied("Отправить можно только свою заявку в черновике.")
    revision = active_revision(project)
    line = revision.lines.select_related("section__parent").filter(key=payment.budget_line_key).first() if revision else None
    if line is None:
        raise ValidationError("Выберите строку действующей сметы.")
    users = [entry.user for entry in project.payment_approvers.select_related("user")]
    if not users:
        raise ValidationError("В настройках бюджета не выбран ни один согласующий.")
    validate_approvers(project, users)
    validate_recipient(payment, project.require_payment_bank_details)
    if payment.events.exclude(project=project).exists():
        raise ValidationError("Мероприятия должны принадлежать этому проекту.")
    payment.line_name = line.name
    payment.section_path = section_path(line.section)
    payment.bank_details_required = project.require_payment_bank_details
    payment.status = "pending"
    payment.submitted_at = timezone.now()
    payment.full_clean()
    payment.save()
    PaymentApproval.objects.bulk_create([PaymentApproval(payment=payment, approver=user, position=i) for i, user in enumerate(users)])
    record(actor, "payment.submitted", payment.pk, project=str(project.pk), amount=str(payment.amount), approver_count=len(users))


def section_path(section):
    return f"{section.parent.name} / {section.name}" if section.parent_id else section.name


@transaction.atomic
def decide_payment(actor, project, payment_id, approve, comment=""):
    project = lock_project(project)
    require_permission(actor, project, PP.APPROVE_PAYMENTS)
    payment = get_object_or_404(project.payment_orders, pk=payment_id)
    vote = payment.approvals.filter(approver=actor).first()
    if vote is None:
        raise PermissionDenied("Вы не входите в список согласующих этой заявки.")
    if payment.status != "pending" or vote.status != "pending":
        raise ValidationError("Решение уже принято или согласование завершено.")
    final = approve and not payment.approvals.exclude(pk=vote.pk).exclude(status="approved").exists()
    if final:
        check_capacity(project, payment)
    vote.status = "approved" if approve else "rejected"
    vote.comment = comment
    vote.decided_at = timezone.now()
    vote.save()
    if final or not approve:
        payment.status = "approved" if final else "rejected"
        payment.approved_at = timezone.now() if final else None
        payment.save()
    record(actor, "payment.approved" if approve else "payment.rejected", payment.pk, project=str(project.pk), final=final, amount=str(payment.amount))


@transaction.atomic
def execute_payment(actor, project, payment_id, document_date, document_number, purpose):
    project = lock_project(project)
    require_permission(actor, project, PP.EXECUTE_PAYMENTS)
    payment = get_object_or_404(project.payment_orders, pk=payment_id)
    if payment.status == "executed":
        return payment
    if payment.status != "approved":
        raise ValidationError("Исполнить можно только согласованный платёж.")
    if not document_date or document_date > timezone.localdate() or not document_number.strip() or not purpose.strip():
        raise ValidationError("Укажите дату не позднее сегодняшней, номер документа и точное назначение платежа.")
    validate_recipient(payment, payment.bank_details_required)
    if not payment.attachments.exists():
        raise ValidationError("Для исполнения прикрепите хотя бы один подтверждающий файл.")
    check_capacity(project, payment, exclude_self=True)
    payment.payment_document_date = document_date
    payment.payment_document_number = document_number.strip()
    payment.payment_purpose = purpose.strip()
    payment.status = "executed"
    payment.executed_at = timezone.now()
    payment.executed_by = actor
    payment.full_clean()
    payment.save()
    record(actor, "payment.executed", payment.pk, project=str(project.pk), amount=str(payment.amount))
    return payment


def may_attach(actor, project, payment):
    if payment.status in ["draft", "pending"] and payment.created_by_id == actor.pk and has_project_permission(actor, project, PP.PREPARE_PAYMENTS):
        return True
    if payment.status == "pending" and has_project_permission(actor, project, PP.APPROVE_PAYMENTS):
        return payment.approvals.filter(approver=actor).exists()
    return payment.status in ["approved", "executed"] and has_project_permission(actor, project, PP.EXECUTE_PAYMENTS)


@transaction.atomic
def add_attachment(actor, project, payment_id, file):
    project = lock_project(project)
    payment = get_object_or_404(project.payment_orders, pk=payment_id)
    if not may_attach(actor, project, payment):
        raise PermissionDenied
    if file.size > 20 * 1024 * 1024:
        raise ValidationError("Размер файла не должен превышать 20 МБ.")
    attachment = PaymentAttachment(payment=payment, file=file,
        original_name=Path(file.name.replace("\\", "/")).name[:255], size=file.size, uploaded_by=actor)
    try:
        attachment.save()
        record(actor, "payment.attachment_added", attachment.pk, project=str(project.pk), payment=payment.pk)
    except Exception:
        if attachment.file and attachment.file._committed:
            attachment.file.delete(save=False)
        raise
    return attachment


@transaction.atomic
def remove_attachment(actor, project, payment_id, attachment_id):
    project = lock_project(project)
    payment = get_object_or_404(project.payment_orders, pk=payment_id)
    require_permission(actor, project, PP.PREPARE_PAYMENTS)
    attachment = get_object_or_404(payment.attachments, pk=attachment_id)
    if payment.status != "draft" or attachment.uploaded_by_id != actor.pk:
        raise PermissionDenied("Удалить можно только свой файл в черновике.")
    storage, name = attachment.file.storage, attachment.file.name
    attachment.delete()
    transaction.on_commit(lambda: storage.delete(name))


@transaction.atomic
def delete_payment(actor, project, payment_id):
    project = lock_project(project)
    require_permission(actor, project, PP.PREPARE_PAYMENTS)
    payment = get_object_or_404(project.payment_orders, pk=payment_id)
    if payment.status != "draft" or payment.created_by_id != actor.pk:
        raise PermissionDenied("Удалить можно только свою заявку до отправки.")
    files = [(item.file.storage, item.file.name) for item in payment.attachments.all()]
    payment.delete()
    for storage, name in files:
        transaction.on_commit(lambda storage=storage, name=name: storage.delete(name))
    record(actor, "payment.draft_deleted", payment_id, project=str(project.pk))
