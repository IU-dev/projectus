"""Vue page API over the existing, permission-checked Django views.

GET/POST with Accept: application/json returns a page envelope. Ordinary
navigation returns the Vue shell. No model fields are serialized implicitly.
"""
import json
from decimal import Decimal
from html import unescape
from urllib.parse import urlsplit

from django import forms
from django.contrib.messages import get_messages
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse, HttpResponseNotAllowed
from django.middleware.csrf import get_token
from django.template.loader import render_to_string
from django.utils.cache import patch_vary_headers
from django.utils.html import strip_tags

from .models import Project, ProjectRequest, ProjectMember, User, AuditEvent
from .forms import ProjectListField
from .models import ProjectIndicator
from .event_data import event_data
from .permissions import SystemPermission, has_system_permission


PAGES = {
    'dashboard', 'my_contracts', 'register', 'login', 'logout', 'verify_email',
    'resend_verification', 'password_reset', 'password_reset_done',
    'password_reset_confirm', 'password_reset_complete', 'password_change',
    'password_change_done', 'request_project', 'project', 'project_edit',
    'members', 'member_edit', 'member_remove', 'revoke_invitation',
    'accept_invitation', 'operations', 'applications', 'decide_application',
    'users', 'staff_permissions', 'staff_user_search', 'audit',
    'project_indicators', 'project_events', 'project_budget', 'project_contracts',
    'indicator_create', 'indicator_edit',
    'event_create', 'event_detail', 'event_plan', 'event_result', 'event_confirm',
    'attachment_upload', 'attachment_remove',
}
PAGES.update({
    'budget_revision', 'budget_clone', 'budget_template', 'budget_section_create',
    'budget_section_edit', 'budget_section_remove', 'budget_line_create', 'budget_line_edit',
    'budget_line_remove', 'budget_publish', 'budget_submit', 'budget_approve', 'budget_reject',
    'budget_settings', 'receipt_create', 'payment_create', 'payment_edit', 'payment_detail',
    'payment_submit', 'payment_approve', 'payment_reject', 'payment_execute', 'payment_remove',
    'payment_attachment_upload', 'payment_attachment_remove',
})


def budget_permissions(user, project):
    from .budget_services import FINANCE_PERMISSIONS
    from .permissions import has_project_permission
    return {str(code): has_project_permission(user, project, code) for code in FINANCE_PERMISSIONS}


def revision_data(revision):
    return {'id': revision.pk, 'number': revision.number, 'kind': revision.kind,
            'kind_label': revision.get_kind_display(), 'status': revision.status,
            'status_label': revision.get_status_display(), 'reason': revision.reason,
            'base_id': revision.base_id, 'created_at': revision.created_at,
            'submitted_at': revision.submitted_at, 'decided_at': revision.decided_at,
            'author': revision.created_by.get_full_name() or revision.created_by.email,
            'decider': (revision.decided_by.get_full_name() or revision.decided_by.email) if revision.decided_by_id else None}


def budget_data(user, project, revision):
    from decimal import Decimal
    from django.db.models import Sum
    from .budget_services import balances, ZERO
    permissions = budget_permissions(user, project)
    rows, totals = [], {name: ZERO for name in ['total_amount', 'cofinancing_amount', 'requested_amount', 'reserved', 'executed']}
    if revision:
        sections = list(revision.sections.all())
        lines = list(revision.lines.all())
        usage = {(entry['budget_line_key'], entry['status']): entry['amount'].quantize(Decimal('0.01')) for entry in project.payment_orders.filter(
            status__in=['approved', 'executed']).values('budget_line_key', 'status').annotate(amount=Sum('amount'))}
        by_section, children = {}, {}
        for line in lines:
            values = {name: getattr(line, name) for name in ['total_amount', 'cofinancing_amount', 'requested_amount']}
            values.update(reserved=usage.get((line.key, 'approved'), ZERO), executed=usage.get((line.key, 'executed'), ZERO))
            values['remaining'] = values['total_amount'] - values['reserved'] - values['executed']
            by_section.setdefault(line.section_id, []).append({
                'type': 'line', 'id': line.pk, 'key': str(line.key), 'name': line.name,
                'unit_price': str(line.unit_price) if line.unit_price is not None else None,
                'quantity': str(line.quantity) if line.quantity is not None else None,
                'unit_name': line.unit_name, 'comment': line.comment,
                'can_remove': values['reserved'] + values['executed'] == ZERO, **values})
            for name in totals:
                totals[name] += values[name]
        for section in sections:
            children.setdefault(section.parent_id, []).append(section)

        def append_section(section, depth):
            start = len(rows)
            row = {'type': 'section', 'id': section.pk, 'name': section.name, 'depth': depth,
                   'explanation': section.explanation, **{name: ZERO for name in totals}}
            rows.append(row)
            for child in children.get(section.pk, []):
                append_section(child, depth + 1)
            for line in by_section.get(section.pk, []):
                rows.append({**line, 'depth': depth + 1})
            for line in rows[start + 1:]:
                if line['type'] == 'line':
                    for name in totals:
                        row[name] += line[name]
            row['remaining'] = row['total_amount'] - row['reserved'] - row['executed']
            row['can_remove'] = row['reserved'] + row['executed'] == ZERO

        for section in children.get(None, []):
            append_section(section, 0)
    totals['remaining'] = totals['total_amount'] - totals['reserved'] - totals['executed']
    for row in rows:
        for key, value in row.items():
            if isinstance(value, Decimal):
                row[key] = str(value)
    history = [revision_data(item) for item in project.budget_revisions.select_related('created_by', 'decided_by')]
    payments = [payment_data(item, user, project, detail=False, permissions=permissions) for item in project.payment_orders.select_related('created_by').prefetch_related('approvals__approver')]
    receipts = [{'id': receipt.pk, 'amount': str(receipt.amount), 'date': receipt.received_date,
                 'comment': receipt.comment, 'author': receipt.created_by.get_full_name() or receipt.created_by.email}
                for receipt in project.fund_receipts.select_related('created_by')]
    return {'permissions': permissions, 'revision': revision_data(revision) if revision else None,
            'editable': bool(revision and revision.status == 'draft' and permissions['edit_budget']),
            'rows': rows, 'totals': {key: str(value) for key, value in totals.items()},
            'balances': {key: str(value) for key, value in balances(project).items()},
            'history': history, 'payments': payments, 'receipts': receipts,
            'can_clone': permissions['edit_budget'] and any(item['status'] == 'active' for item in history) and not any(item['status'] in ['draft', 'pending'] for item in history)}


def payment_data(payment, user, project, detail=True, permissions=None):
    from .budget_services import may_attach
    approvals = list(payment.approvals.all())
    permissions = permissions if permissions is not None else budget_permissions(user, project)
    prepare = permissions['prepare_payments']
    execute = permissions['execute_payments']
    vote = next((vote for vote in approvals if vote.approver_id == user.pk), None)
    data = {'id': payment.pk, 'number': payment.number, 'amount': str(payment.amount),
            'status': payment.status, 'status_label': payment.get_status_display(),
            'line_name': payment.line_name, 'section_path': payment.section_path,
            'description': payment.description, 'recipient_name': payment.recipient_name,
            'payment_purpose': payment.payment_purpose, 'approved_count': sum(v.status == 'approved' for v in approvals),
            'approver_count': len(approvals),
            'can_edit': prepare and payment.created_by_id == user.pk and payment.status == 'draft',
            'can_vote': payment.status == 'pending' and bool(vote and vote.status == 'pending') and permissions['approve_payments'],
            'can_execute': execute and payment.status == 'approved'}
    if detail:
        data.update(
            recipient_type=payment.get_recipient_type_display(), inn=payment.inn, kpp=payment.kpp,
            account=payment.account, bank_name=payment.bank_name, bik=payment.bik,
            correspondent_account=payment.correspondent_account,
            bank_details_required=project.require_payment_bank_details if payment.status == 'draft' else payment.bank_details_required,
            author=payment.created_by.get_full_name() or payment.created_by.email,
            created_at=payment.created_at, submitted_at=payment.submitted_at,
            approved_at=payment.approved_at, executed_at=payment.executed_at,
            executor=(payment.executed_by.get_full_name() or payment.executed_by.email) if payment.executed_by_id else None,
            payment_document_date=payment.payment_document_date, payment_document_number=payment.payment_document_number,
            can_attach=may_attach(user, project, payment),
            approvals=[{'id': vote.pk, 'name': vote.approver.get_full_name() or vote.approver.email,
                        'status': vote.status, 'status_label': vote.get_status_display(), 'comment': vote.comment, 'decided_at': vote.decided_at} for vote in approvals],
            events=[{'id': event.pk, 'title': event.title} for event in payment.events.all()],
            attachments=[{'id': file.pk, 'name': file.original_name, 'size': file.size,
                          'created_at': file.created_at, 'author': file.uploaded_by.get_full_name() or file.uploaded_by.email,
                          'can_remove': payment.status == 'draft' and prepare and file.uploaded_by_id == user.pk}
                         for file in payment.attachments.all()])
    return data


def wants_json(request):
    return 'application/json' in request.headers.get('Accept', '')


def user_data(user):
    return {
        'id': user.pk, 'email': user.email, 'name': user.get_full_name(),
        'email_verified': user.email_verified, 'is_superuser': user.is_superuser,
        'permissions': [{'code': grant.code, 'label': grant.get_code_display()}
                        for grant in user.system_grants.all()],
    }


def object_data(obj):
    if isinstance(obj, ProjectIndicator):
        return {'id': obj.pk, 'title': obj.title, 'kind': obj.kind, 'kind_label': obj.get_kind_display(),
                'target_value': obj.target_value, 'current_value': obj.current_value, 'unit': obj.unit,
                'result': obj.result, 'achieved': obj.achieved, 'progress_percent': obj.progress_percent}
    if isinstance(obj, Project):
        return {'id': str(obj.pk), 'title': obj.title, 'description': obj.description,
                'goals': obj.goals, 'tasks': obj.tasks,
                'start_date': obj.start_date, 'end_date': obj.end_date,
                'created_at': obj.created_at, 'owner': {'id': obj.owner_id, 'email': obj.owner.email}}
    if isinstance(obj, ProjectRequest):
        return {'id': obj.pk, 'title': obj.title, 'description': obj.description,
                'created_at': obj.created_at, 'status': obj.status,
                'status_label': obj.get_status_display(), 'decision_note': obj.decision_note,
                'applicant': obj.applicant.email}
    if isinstance(obj, ProjectMember):
        return {'id': obj.pk, 'email': obj.user.email,
                'permissions': [{'code': grant.code, 'label': grant.get_code_display()}
                                for grant in obj.grants.all()]}
    if isinstance(obj, User):
        return user_data(obj)
    if isinstance(obj, AuditEvent):
        return {'id': obj.pk, 'created_at': obj.created_at,
                'actor': obj.actor.email if obj.actor else None,
                'action': obj.action, 'target': obj.target, 'details': obj.details}
    raise TypeError(f'Unsupported page object: {type(obj).__name__}')


def form_data(form):
    fields = []
    for bound in form:
        field = bound.field
        if isinstance(field, ProjectListField):
            kind, value = 'text-list', bound.value() or ['']
        elif isinstance(field.widget, forms.HiddenInput):
            kind, value = 'hidden', bound.value() or ''
        elif isinstance(field.widget, forms.PasswordInput):
            kind, value = 'password', ''
        elif isinstance(field, forms.BooleanField):
            kind, value = 'checkbox', bool(bound.value())
        elif isinstance(field, forms.MultipleChoiceField):
            kind, value = 'checkboxes', bound.value() or []
        elif isinstance(field, forms.ChoiceField):
            choices = list(field.choices)
            kind = 'select'
            value = bound.value() if bound.value() is not None else (choices[0][0] if choices else '')
        elif isinstance(field, forms.DateField):
            kind, value = 'date', bound.value() or ''
            if hasattr(value, 'isoformat'):
                value = value.isoformat()
        elif isinstance(field, forms.DecimalField):
            kind, value = 'number', bound.value() if bound.value() is not None else ''
        elif isinstance(field, forms.FileField):
            kind, value = 'file', ''
        else:
            kind = ('textarea' if isinstance(field.widget, forms.Textarea) else
                    'email' if isinstance(field, forms.EmailField) else 'text')
            value = bound.value() or ''
        fields.append({
            'name': bound.name, 'label': str(bound.label), 'kind': kind, 'value': value,
            'required': field.required, 'max_length': getattr(field, 'max_length', None),
            'disabled': field.disabled,
            'min': getattr(field, 'min_value', None),
            'step': str(Decimal(1).scaleb(-field.decimal_places)) if isinstance(field, forms.DecimalField) and field.decimal_places is not None else None,
            'show_when': getattr(field, 'show_when', None),
            'help': unescape(strip_tags(str(field.help_text))),
            'errors': list(bound.errors),
            'choices': [{'value': str(code), 'label': str(label)}
                        for code, label in getattr(field, 'choices', [])],
        })
    return {'fields': fields, 'errors': list(form.non_field_errors())}


def envelope(request):
    user = request.user
    return {
        'user': user_data(user) if user.is_authenticated else None,
        'show_operations': any(has_system_permission(user, code) for code in SystemPermission),
        'csrf_token': get_token(request),
        'messages': [{'text': str(message), 'level': message.tags}
                     for message in get_messages(request)],
    }


def page_data(request, context):
    payload = envelope(request)
    payload['page'] = context.get('page', request.resolver_match.url_name)
    payload['data'] = data = {}
    for key in ('budget', 'payment', 'tab', 'back_url'):
        if key in context:
            data[key] = context[key]
    for key in ('title', 'subtitle', 'button', 'description', 'owner', 'can_edit',
                'can_requests', 'can_users', 'can_audit', 'can_approve', 'validlink', 'next', 'granted',
                'can_plan', 'can_record', 'can_confirm'):
        if key in context:
            data[key] = context[key]
    if context.get('form') is not None:
        data['form'] = form_data(context['form'])
    if 'project' in context:
        data['project'] = object_data(context['project'])
    if 'project_events' in context:
        data['project_events'] = [event_data(event) for event in context['project_events']]
    if 'event' in context:
        data['event'] = event_data(context['event'])
    if 'selected_user' in context:
        data['selected_user'] = user_data(context['selected_user']) if context['selected_user'] else None
    for key in ('projects', 'applications', 'members', 'users', 'staff', 'events', 'indicators'):
        if key not in context:
            continue
        collection = context[key]
        data[key] = [object_data(obj) for obj in collection]
        if hasattr(collection, 'paginator'):
            data['pagination'] = {'page': collection.number, 'pages': collection.paginator.num_pages,
                                  'count': collection.paginator.count}
    if 'invitations' in context:
        data['invitations'] = [
            {'id': str(inv.pk), 'email': inv.email, 'expires_at': inv.expires_at, 'link': link}
            for inv, link in context['invitations']
        ]
    return payload


class FrontendMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def process_view(self, request, view, args, kwargs):
        if request.resolver_match.url_name in PAGES and request.method not in {'GET', 'HEAD', 'POST'}:
            return HttpResponseNotAllowed(['GET', 'HEAD', 'POST'])

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, 'resolver_match', None)
        if not match or match.url_name not in PAGES:
            return response
        if wants_json(request):
            if 300 <= response.status_code < 400 and response.get('Location'):
                payload = envelope(request)
                payload['redirect'] = response['Location']
                # Expired sessions remain distinguishable from successful mutations.
                login_redirect = urlsplit(response['Location']).path == '/login/' and not request.user.is_authenticated and request.method == 'GET'
                response = JsonResponse(payload, status=401 if login_redirect else 200)
            elif not response.get('Content-Type', '').startswith('application/json'):
                errors = {403: 'Доступ запрещен. Проверьте права и обновите страницу.',
                          404: 'Страница не найдена.', 405: 'Метод запроса не поддерживается.',
                          429: 'Слишком много запросов. Повторите через 15 минут.'}
                response = JsonResponse({'error': errors.get(response.status_code, 'Не удалось выполнить запрос.')}, status=response.status_code)
        patch_vary_headers(response, ['Accept', 'Cookie'])
        response['Cache-Control'] = 'no-store'
        return response

    def process_template_response(self, request, response):
        if not request.resolver_match or request.resolver_match.url_name not in PAGES:
            return response
        payload = page_data(request, response.context_data or {})
        if wants_json(request):
            response.template_name = 'api.json'
            response.context_data = {'payload': json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False)}
            response['Content-Type'] = 'application/json'
            form = payload['data'].get('form')
            if request.method == 'POST' and form and (form['errors'] or any(field['errors'] for field in form['fields'])):
                response.status_code = 422
        else:
            # Progressive fallback keeps ordinary server forms usable without JS.
            fallback = render_to_string(response.template_name, response.context_data, request=request)
            fallback = fallback.split('<body>', 1)[-1].rsplit('</body>', 1)[0]
            response.template_name = 'app.html'
            response.context_data = {'bootstrap': payload, 'fallback': fallback}
        return response
