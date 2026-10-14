from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from . import budget_services as service
from .budget_forms import (SectionForm, LineForm, TemplateForm, RevisionForm, SettingsForm,
                           ReceiptForm, PaymentForm, ExecutionForm, AttachmentForm, DecisionForm)
from .frontend import budget_data, payment_data
from .models import BudgetSection, BudgetLine, FundReceipt, PaymentOrder, PaymentAttachment
from .permissions import ProjectPermission as PP, has_project_permission
from .services import record
from .views import verified_required, accessible_project, render


def finance_project(request, pk, permission=None):
    project = accessible_project(request, pk)
    if not any(has_project_permission(request.user, project, code) for code in service.FINANCE_PERMISSIONS):
        raise PermissionDenied
    if permission:
        service.require_permission(request.user, project, permission)
    return project


def locked_finance_project(request, pk, permission):
    project = service.lock_project(finance_project(request, pk, permission))
    service.require_permission(request.user, project, permission)
    return project


def budget_url(project, revision=None):
    return reverse('budget_revision', args=[project.pk, revision.pk]) if revision else reverse('project_budget', args=[project.pk])


def form_page(request, project, form, title, back_url=None, button='Сохранить'):
    return render(request, 'budget_form.html', {'project': project, 'form': form,
        'title': title, 'button': button, 'back_url': back_url or budget_url(project)})


def form_service(form, callback):
    """Services use a savepoint so rejected transitions leave no partial state."""
    try:
        with transaction.atomic():
            return True, callback()
    except ValidationError as exc:
        form.add_error(None, ' '.join(exc.messages))
        return False, None


@verified_required
@require_GET
def budget(request, pk, revision_id=None):
    project = finance_project(request, pk)
    service.ensure_initial(project, request.user)
    revision = get_object_or_404(project.budget_revisions.select_related('created_by', 'decided_by'), pk=revision_id) if revision_id else (
        service.active_revision(project) or project.budget_revisions.select_related('created_by', 'decided_by').first())
    tab = request.GET.get('tab', 'estimate')
    if tab not in ['estimate', 'payments', 'receipts', 'history']:
        tab = 'estimate'
    return render(request, 'budget.html', {'project': project, 'budget': budget_data(request.user, project, revision), 'tab': tab})


@verified_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def section_edit(request, pk, revision_id, section_id=None):
    project = locked_finance_project(request, pk, PP.EDIT_BUDGET)
    revision = service.editable_revision(project, revision_id)
    section = get_object_or_404(revision.sections, pk=section_id) if section_id else BudgetSection(revision=revision)
    form = SectionForm(request.POST if request.method == 'POST' else None, instance=section, revision=revision)
    if request.method == 'POST' and form.is_valid():
        form.save()
        record(request.user, 'budget.section_saved', section.pk, project=str(project.pk), revision=revision.pk)
        return redirect(budget_url(project, revision))
    return form_page(request, project, form, 'Статья сметы', budget_url(project, revision))


@verified_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def line_edit(request, pk, revision_id, line_id=None):
    project = locked_finance_project(request, pk, PP.EDIT_BUDGET)
    revision = service.editable_revision(project, revision_id)
    line = get_object_or_404(revision.lines, pk=line_id) if line_id else BudgetLine(revision=revision)
    form = LineForm(request.POST if request.method == 'POST' else None, instance=line, revision=revision)
    if request.method == 'POST' and form.is_valid():
        form.save()
        record(request.user, 'budget.line_saved', line.pk, project=str(project.pk), revision=revision.pk)
        return redirect(budget_url(project, revision))
    return form_page(request, project, form, 'Строка сметы', budget_url(project, revision))


@verified_required
@require_http_methods(['GET', 'POST'])
def revision_clone(request, pk):
    project = finance_project(request, pk, PP.EDIT_BUDGET)
    form = RevisionForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        ok, revision = form_service(form, lambda: service.clone_revision(request.user, project, **form.cleaned_data))
        if ok:
            return redirect(budget_url(project, revision))
    return form_page(request, project, form, 'Новая версия сметы', button='Создать черновик')


@verified_required
@require_http_methods(['GET', 'POST'])
def template_apply(request, pk, revision_id):
    project = finance_project(request, pk, PP.EDIT_BUDGET)
    revision = service.editable_revision(project, revision_id)
    form = TemplateForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        ok, _ = form_service(form, lambda: service.apply_template(request.user, project, revision_id, form.cleaned_data['template']))
        if ok:
            return redirect(budget_url(project, revision))
    return form_page(request, project, form, 'Применить шаблон статей', budget_url(project, revision), 'Применить')


def revision_transition(request, pk, revision_id, callback, title, permission):
    project = finance_project(request, pk, permission)
    revision = get_object_or_404(project.budget_revisions, pk=revision_id)
    form = DecisionForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        ok, _ = form_service(form, lambda: callback(request.user, project, revision_id))
        if ok:
            messages.success(request, 'Состояние сметы обновлено.')
            return redirect(budget_url(project, revision))
    return form_page(request, project, form, title, budget_url(project, revision), title)


@verified_required
@require_http_methods(['GET', 'POST'])
def revision_publish(request, pk, revision_id):
    return revision_transition(request, pk, revision_id, service.publish_initial, 'Опубликовать исходную смету', PP.EDIT_BUDGET)


@verified_required
@require_http_methods(['GET', 'POST'])
def revision_submit(request, pk, revision_id):
    return revision_transition(request, pk, revision_id, service.submit_revision, 'Отправить изменение на согласование', PP.EDIT_BUDGET)


@verified_required
@require_http_methods(['GET', 'POST'])
def revision_approve(request, pk, revision_id):
    return revision_transition(request, pk, revision_id, lambda *args: service.decide_revision(*args, approve=True), 'Согласовать изменение', PP.APPROVE_BUDGET_CHANGES)


@verified_required
@require_http_methods(['GET', 'POST'])
def revision_reject(request, pk, revision_id):
    return revision_transition(request, pk, revision_id, lambda *args: service.decide_revision(*args, approve=False), 'Отклонить изменение', PP.APPROVE_BUDGET_CHANGES)


def remove_estimate_item(request, pk, revision_id, item_id, line=False):
    with transaction.atomic():
        project = locked_finance_project(request, pk, PP.EDIT_BUDGET)
        revision = service.editable_revision(project, revision_id)
        item = get_object_or_404(revision.lines if line else revision.sections, pk=item_id)
        keys = [item.key] if line else list(revision.lines.filter(section_id__in=[item.pk, *item.children.values_list('pk', flat=True)]).values_list('key', flat=True))
        if project.payment_orders.filter(budget_line_key__in=keys, status__in=['approved', 'executed']).exists():
            form = DecisionForm(request.POST)
            form.is_valid()
            form.add_error(None, 'Нельзя удалить строку с согласованным или исполненным платежом.')
            return form_page(request, project, form, 'Удаление строки сметы', budget_url(project, revision))
        if not line:
            revision.lines.filter(key__in=keys).delete()
        item.delete()
        record(request.user, 'budget.item_deleted', item_id, project=str(project.pk), revision=revision.pk)
        return redirect(budget_url(project, revision))


@verified_required
@require_POST
def line_remove(request, pk, revision_id, line_id):
    return remove_estimate_item(request, pk, revision_id, line_id, line=True)


@verified_required
@require_POST
def section_remove(request, pk, revision_id, section_id):
    return remove_estimate_item(request, pk, revision_id, section_id)


@verified_required
@require_http_methods(['GET', 'POST'])
def settings(request, pk):
    project = finance_project(request, pk, PP.EDIT_BUDGET)
    form = SettingsForm(request.POST if request.method == 'POST' else None, project=project)
    selected = [entry.user for entry in project.payment_approvers.select_related('user')]
    if request.method == 'GET':
        try:
            service.validate_approvers(project, selected)
        except ValidationError as exc:
            form.cleaned_data = {}
            form.add_error(None, 'Ошибка настройки: ' + ' '.join(exc.messages))
    if request.method == 'POST' and form.is_valid():
        ok, _ = form_service(form, lambda: service.save_settings(request.user, project, form.cleaned_data['approvers'], form.cleaned_data['require_payment_bank_details']))
        if ok:
            return redirect(budget_url(project))
    return form_page(request, project, form, 'Настройки бюджета')


@verified_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def receipt_create(request, pk):
    project = locked_finance_project(request, pk, PP.RECORD_RECEIPTS)
    form = ReceiptForm(request.POST if request.method == 'POST' else None, instance=FundReceipt(project=project, created_by=request.user))
    if request.method == 'POST' and form.is_valid():
        receipt = form.save()
        record(request.user, 'receipt.created', receipt.pk, project=str(project.pk), amount=str(receipt.amount))
        return redirect(budget_url(project) + '?tab=receipts')
    return form_page(request, project, form, 'Поступление средств')


@verified_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def payment_edit(request, pk, payment_id=None):
    project = locked_finance_project(request, pk, PP.PREPARE_PAYMENTS)
    payment = get_object_or_404(project.payment_orders, pk=payment_id) if payment_id else PaymentOrder(project=project, created_by=request.user)
    if payment.status != 'draft' or payment.created_by_id != request.user.pk:
        raise PermissionDenied('Изменять можно только свою заявку в черновике.')
    form = PaymentForm(request.POST if request.method == 'POST' else None, instance=payment, project=project)
    if request.method == 'POST' and form.is_valid():
        line = form.lines[form.cleaned_data['budget_line']]
        payment = form.save(commit=False)
        payment.budget_line_key = line.key
        payment.line_name = line.name
        payment.section_path = service.section_path(line.section)
        if not payment_id:
            project.payment_sequence += 1
            project.save(update_fields=['payment_sequence'])
            payment.number = project.payment_sequence
        payment.save()
        payment.events.set(form.cleaned_data['events'])
        record(request.user, 'payment.updated' if payment_id else 'payment.created', payment.pk, project=str(project.pk), amount=str(payment.amount))
        return redirect('payment_detail', pk=pk, payment_id=payment.pk)
    return form_page(request, project, form, 'Заявка на оплату')


def payment_query(project):
    return project.payment_orders.select_related('created_by', 'executed_by').prefetch_related('approvals__approver', 'events', 'attachments__uploaded_by')


@verified_required
@require_GET
def payment_detail(request, pk, payment_id):
    project = finance_project(request, pk)
    payment = get_object_or_404(payment_query(project), pk=payment_id)
    data = payment_data(payment, request.user, project)
    return render(request, 'payment.html', {'project': project, 'payment': data, 'form': AttachmentForm() if data['can_attach'] else None})


def payment_transition(request, pk, payment_id, title, permission, callback, execution=False):
    project = finance_project(request, pk, permission)
    payment = get_object_or_404(project.payment_orders, pk=payment_id)
    if permission == PP.APPROVE_PAYMENTS and not payment.approvals.filter(approver=request.user).exists():
        raise PermissionDenied
    if permission == PP.PREPARE_PAYMENTS and payment.created_by_id != request.user.pk:
        raise PermissionDenied
    form = (ExecutionForm if execution else DecisionForm)(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        ok, _ = form_service(form, lambda: callback(request.user, project, payment_id, form.cleaned_data))
        if ok:
            messages.success(request, 'Состояние платежа обновлено.')
            return redirect('payment_detail', pk=pk, payment_id=payment_id)
    return form_page(request, project, form, title, reverse('payment_detail', args=[pk, payment_id]), title)


@verified_required
@require_http_methods(['GET', 'POST'])
def payment_submit(request, pk, payment_id):
    return payment_transition(request, pk, payment_id, 'Отправить заявку на согласование', PP.PREPARE_PAYMENTS,
        lambda actor, project, payment_id, data: service.submit_payment(actor, project, payment_id))


@verified_required
@require_http_methods(['GET', 'POST'])
def payment_approve(request, pk, payment_id):
    return payment_transition(request, pk, payment_id, 'Одобрить платёж', PP.APPROVE_PAYMENTS,
        lambda actor, project, payment_id, data: service.decide_payment(actor, project, payment_id, True, data['comment']))


@verified_required
@require_http_methods(['GET', 'POST'])
def payment_reject(request, pk, payment_id):
    return payment_transition(request, pk, payment_id, 'Отклонить платёж', PP.APPROVE_PAYMENTS,
        lambda actor, project, payment_id, data: service.decide_payment(actor, project, payment_id, False, data['comment']))


@verified_required
@require_http_methods(['GET', 'POST'])
def payment_execute(request, pk, payment_id):
    return payment_transition(request, pk, payment_id, 'Исполнить платёж', PP.EXECUTE_PAYMENTS,
        lambda actor, project, payment_id, data: service.execute_payment(actor, project, payment_id,
            data['payment_document_date'], data['payment_document_number'], data['payment_purpose']), execution=True)


@verified_required
@require_POST
def payment_remove(request, pk, payment_id):
    project = finance_project(request, pk, PP.PREPARE_PAYMENTS)
    service.delete_payment(request.user, project, payment_id)
    return redirect(budget_url(project) + '?tab=payments')


@verified_required
@require_http_methods(['GET', 'POST'])
def attachment_upload(request, pk, payment_id):
    project = finance_project(request, pk)
    payment = get_object_or_404(payment_query(project), pk=payment_id)
    if not service.may_attach(request.user, project, payment):
        raise PermissionDenied
    form = AttachmentForm(request.POST if request.method == 'POST' else None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        ok, _ = form_service(form, lambda: service.add_attachment(request.user, project, payment_id, form.cleaned_data['file']))
        if ok:
            return redirect('payment_detail', pk=pk, payment_id=payment_id)
    return render(request, 'payment.html', {'page': 'payment_detail', 'project': project,
        'payment': payment_data(payment, request.user, project), 'form': form})


@verified_required
@require_POST
def attachment_remove(request, pk, payment_id, attachment_id):
    project = finance_project(request, pk)
    service.remove_attachment(request.user, project, payment_id, attachment_id)
    return redirect('payment_detail', pk=pk, payment_id=payment_id)


@verified_required
@require_GET
def attachment_download(request, pk, payment_id, attachment_id):
    project = finance_project(request, pk)
    attachment = get_object_or_404(PaymentAttachment, pk=attachment_id, payment_id=payment_id, payment__project=project)
    try:
        file = attachment.file.open('rb')
    except FileNotFoundError:
        raise Http404
    response = FileResponse(file, as_attachment=True, filename=attachment.original_name, content_type='application/octet-stream')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
