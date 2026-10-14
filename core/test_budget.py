from datetime import timedelta
from decimal import Decimal as D
import tempfile

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from . import budget_services as service
from .budget_forms import PaymentForm
from .frontend import budget_data
from .models import (User, Project, ProjectRequest, ProjectMember, BudgetRevision, BudgetSection,
                     BudgetLine, BudgetTemplate, BudgetTemplateItem, PaymentOrder,
                     FundReceipt, ProjectEvent, AuditEvent, SystemPermissions)
from .permissions import ProjectPermission as PP, SystemPermission as SP


class BudgetTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('budget-owner@example.com', email_verified=True)
        self.editor = User.objects.create_user('budget-editor@example.com', email_verified=True)
        self.approver = User.objects.create_user('budget-approver@example.com', email_verified=True)
        self.outsider = User.objects.create_superuser('budget-root@example.com')
        self.project = self.make_project(self.owner)
        self.editor_member = ProjectMember.objects.create(project=self.project, user=self.editor)
        self.approver_member = ProjectMember.objects.create(project=self.project, user=self.approver)
        self.approver_member.grants.create(code=PP.APPROVE_PAYMENTS)
        self.revision = service.ensure_initial(self.project, self.owner)
        self.section = BudgetSection.objects.create(revision=self.revision, name='Расходы')
        self.line = self.make_line(self.section)
        self.client.force_login(self.owner)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        from django.test import override_settings
        self.media = override_settings(MEDIA_ROOT=self.temp.name)
        self.media.enable()
        self.addCleanup(self.media.disable)

    def make_project(self, owner):
        application = ProjectRequest.objects.create(applicant=owner, title='Проект')
        return Project.objects.create(owner=owner, request=application, title=application.title)

    def make_line(self, section, total='100.00', co='20.00', name='Работы'):
        return BudgetLine.objects.create(revision=section.revision, section=section, name=name,
            total_amount=D(total), cofinancing_amount=D(co), requested_amount=D(total)-D(co))

    def url(self, name, *ids, project=None):
        return reverse(name, args=[(project or self.project).pk, *ids])

    def post(self, name, data=None, *ids, project=None):
        return self.client.post(self.url(name, *ids, project=project), data or {}, HTTP_ACCEPT='application/json')

    def get(self, name, *ids, project=None):
        return self.client.get(self.url(name, *ids, project=project), HTTP_ACCEPT='application/json')

    def activate(self, received='200.00', approvers=None, required=False):
        service.publish_initial(self.owner, self.project, self.revision.pk)
        if received:
            FundReceipt.objects.create(project=self.project, amount=D(received), received_date=timezone.localdate(), comment='Финансирование', created_by=self.owner)
        service.save_settings(self.owner, self.project, approvers or [self.owner], required)
        self.project.refresh_from_db()

    def payment_values(self, **overrides):
        return {'budget_line': str(self.line.key), 'amount': '60.00', 'description': 'Оплата работ',
                'recipient_type': 'fl', 'recipient_name': 'Иван Иванов', 'inn': '123456789012',
                'kpp': '', 'account': '', 'bank_name': '', 'bik': '', 'correspondent_account': '', **overrides}

    def create_payment(self, **overrides):
        response = self.post('payment_create', self.payment_values(**overrides))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('redirect', response.json())
        return self.project.payment_orders.order_by('-number').first()

    def upload(self, payment, name='proof.pdf'):
        return service.add_attachment(self.owner, self.project, payment.pk, SimpleUploadedFile(name, b'evidence'))

    def test_independent_permissions_revocation_and_system_isolation(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.get('project_budget').status_code, 403)
        for code in service.FINANCE_PERMISSIONS:
            self.editor_member.grants.all().delete()
            self.editor_member.grants.create(code=code)
            response = self.get('project_budget')
            self.assertEqual(response.status_code, 200)
            granted = response.json()['data']['budget']['permissions']
            self.assertEqual([key for key, value in granted.items() if value], [str(code)])
            self.assertEqual(self.get('receipt_create').status_code, 200 if code == PP.RECORD_RECEIPTS else 403)
            self.assertEqual(self.get('budget_settings').status_code, 200 if code == PP.EDIT_BUDGET else 403)
        self.editor_member.grants.all().delete()
        self.assertEqual(self.get('project_budget').status_code, 403)
        self.client.force_login(self.outsider)
        SystemPermissions.objects.create(user=self.outsider, code=SP.APPROVE_PROJECTS)
        self.assertEqual(self.get('project_budget').status_code, 404)
        self.assertEqual(self.get('payment_create').status_code, 404)
        self.client.force_login(self.owner)
        self.assertTrue(all(self.get('project_budget').json()['data']['budget']['permissions'].values()))

    def test_initial_template_manual_lines_totals_and_constraints(self):
        self.assertEqual(service.ensure_initial(self.project, self.owner).pk, self.revision.pk)
        self.line.delete()
        self.section.delete()
        template = BudgetTemplate.objects.create(name='Типовые статьи')
        parent = BudgetTemplateItem.objects.create(template=template, name='Организация')
        BudgetTemplateItem.objects.create(template=template, parent=parent, name='Услуги')
        service.apply_template(self.owner, self.project, self.revision.pk, template.pk)
        with self.assertRaises(ValidationError):
            service.apply_template(self.owner, self.project, self.revision.pk, template.pk)
        section = self.revision.sections.get(parent__isnull=False)
        self.line = self.make_line(section)
        bad = BudgetLine(revision=self.revision, section=section, name='Ошибка', total_amount=D('100'), cofinancing_amount=D('30'), requested_amount=D('80'))
        with self.assertRaises(ValidationError):
            bad.full_clean()
        bad.requested_amount = D('70')
        bad.unit_price, bad.quantity, bad.unit_name = D('33.33'), D('3'), 'шт.'
        with self.assertRaises(ValidationError):
            bad.full_clean()
        tiny = self.make_line(section, '0.30', '0.10', 'Копейки')
        tiny.full_clean()
        service.publish_initial(self.owner, self.project, self.revision.pk)
        data = budget_data(self.owner, self.project, self.revision)
        for row in [*data['rows'][:2], data['totals']]:
            self.assertEqual(D(row['total_amount']), D('100.30'))
            self.assertEqual(D(row['cofinancing_amount']), D('20.10'))
            self.assertEqual(D(row['requested_amount']), D('80.20'))
        self.assertEqual(self.post('budget_line_edit', {'name': 'Изменение'}, self.revision.pk, self.line.pk).status_code, 403)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BudgetLine.objects.create(revision=self.revision, section=section, name='Неверный итог', total_amount=10, cofinancing_amount=1, requested_amount=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BudgetLine.objects.create(revision=self.revision, section=section, name='Нет пары', total_amount=10, cofinancing_amount=0, requested_amount=10, quantity=1, unit_name='шт.')

    def test_hierarchy_cross_revision_and_unit_validation(self):
        response = self.post('budget_section_create', {'name': 'Подстатья', 'parent': self.section.pk, 'position': 0}, self.revision.pk)
        self.assertEqual(response.status_code, 422)
        other = self.make_project(self.owner)
        revision = service.ensure_initial(other, self.owner)
        foreign = BudgetSection.objects.create(revision=revision, name='Чужая')
        values = {'name': 'Новая строка', 'section': foreign.pk, 'total_amount': '0.30', 'cofinancing_amount': '0.10', 'requested_amount': '0.20', 'position': 0}
        self.assertEqual(self.post('budget_line_create', values, self.revision.pk).status_code, 422)
        values['section'] = self.section.pk
        self.assertIn('redirect', self.post('budget_line_create', values, self.revision.pk).json())
        for price, quantity, unit, total in [('1.00', '', '', '1.00'), ('1.00', '2.000', '', '2.00'), ('1.00', '2.000', 'шт.', '3.00')]:
            response = self.post('budget_line_create', {**values, 'unit_price': price, 'quantity': quantity, 'unit_name': unit, 'total_amount': total, 'cofinancing_amount': '0', 'requested_amount': total}, self.revision.pk)
            self.assertEqual(response.status_code, 422)
        response = self.post('budget_line_create', {**values, 'unit_price': '0.01', 'quantity': '1.500', 'unit_name': 'шт.', 'total_amount': '0.02', 'cofinancing_amount': '0.02', 'requested_amount': '0'}, self.revision.pk)
        self.assertIn('redirect', response.json())

    def test_amendment_transfer_and_immutable_history(self):
        second = self.make_line(self.section, '100', '0', 'Материалы')
        self.activate()
        revision = service.clone_revision(self.owner, self.project, 'transfer', 'Перераспределение')
        self.assertEqual(set(revision.lines.values_list('key', flat=True)), {self.line.key, second.key})
        with self.assertRaises(ValidationError):
            service.clone_revision(self.owner, self.project, 'amendment', 'Ещё одно')
        with self.assertRaises(ValidationError):
            service.submit_revision(self.owner, self.project, revision.pk)
        first = revision.lines.get(key=self.line.key)
        first.total_amount, first.requested_amount = D('80'), D('60')
        first.save()
        with self.assertRaises(ValidationError):
            service.submit_revision(self.owner, self.project, revision.pk)
        target = revision.lines.get(key=second.key)
        target.total_amount = target.requested_amount = D('120')
        target.save()
        service.submit_revision(self.owner, self.project, revision.pk)
        service.decide_revision(self.owner, self.project, revision.pk, True)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.status, 'superseded')
        revision = service.clone_revision(self.owner, self.project, 'amendment', 'Дополнение')
        service.submit_revision(self.owner, self.project, revision.pk)
        service.decide_revision(self.owner, self.project, revision.pk, False)
        self.assertEqual(self.post('budget_section_create', {'name': 'Нельзя'}, revision.pk).status_code, 403)
        self.assertEqual(self.get('budget_revision', self.revision.pk).status_code, 200)

    def test_reserved_and_executed_limits_protect_revisions_and_aggregates(self):
        self.activate()
        payment = self.create_payment()
        service.submit_payment(self.owner, self.project, payment.pk)
        service.decide_payment(self.owner, self.project, payment.pk, True)
        revision = service.clone_revision(self.owner, self.project, 'amendment', 'Уточнение')
        line = revision.lines.get(key=self.line.key)
        self.assertEqual(self.post('budget_line_remove', {}, revision.pk, line.pk).status_code, 422)
        self.assertTrue(revision.lines.filter(pk=line.pk).exists())
        line.total_amount, line.requested_amount = D('50'), D('30')
        line.save()
        with self.assertRaises(ValidationError):
            service.submit_revision(self.owner, self.project, revision.pk)
        line.total_amount, line.requested_amount = D('100'), D('80')
        line.save()
        service.submit_revision(self.owner, self.project, revision.pk)
        line.total_amount, line.requested_amount = D('50'), D('30')
        line.save()  # Simulates a stale proposal; the approval must recheck.
        with self.assertRaises(ValidationError):
            service.decide_revision(self.owner, self.project, revision.pk, True)
        self.upload(payment)
        service.execute_payment(self.owner, self.project, payment.pk, timezone.localdate(), '0001', 'Оплата работ')
        with self.assertRaises(ValidationError):
            service.decide_revision(self.owner, self.project, revision.pk, True)
        data = budget_data(self.owner, self.project, self.revision)
        for row in [data['rows'][0], data['rows'][1], data['totals']]:
            self.assertEqual(D(row['executed']), D('60'))
            self.assertEqual(D(row['remaining']), D('40'))

    def test_specific_approvers_snapshot_all_votes_rejection_and_revocation(self):
        self.activate(approvers=[self.owner, self.approver])
        payment = self.create_payment()
        service.submit_payment(self.owner, self.project, payment.pk)
        service.save_settings(self.owner, self.project, [self.owner], True)
        payment.refresh_from_db()
        self.assertFalse(payment.bank_details_required)
        self.assertEqual(payment.approvals.count(), 2)
        self.editor_member.grants.create(code=PP.APPROVE_PAYMENTS)
        with self.assertRaises(PermissionDenied):
            service.decide_payment(self.editor, self.project, payment.pk, True)
        service.decide_payment(self.owner, self.project, payment.pk, True)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(service.balances(self.project)['reserved'], D('0'))
        with self.assertRaises(ValidationError):
            service.decide_payment(self.owner, self.project, payment.pk, True)
        self.approver_member.grants.all().delete()
        with self.assertRaises(PermissionDenied):
            service.decide_payment(self.approver, self.project, payment.pk, True)
        self.approver_member.grants.create(code=PP.APPROVE_PAYMENTS)
        service.decide_payment(self.approver, self.project, payment.pk, False, 'Отказ')
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'rejected')
        self.assertEqual(service.balances(self.project)['reserved'], D('0'))

    def test_funds_and_line_capacity_two_successive_payments_no_failed_vote(self):
        self.activate(received='90')
        first = self.create_payment()
        service.submit_payment(self.owner, self.project, first.pk)
        service.decide_payment(self.owner, self.project, first.pk, True)
        second = self.create_payment(amount='40.00')
        service.submit_payment(self.owner, self.project, second.pk)
        with self.assertRaisesMessage(ValidationError, 'Недостаточно доступных средств'):
            service.decide_payment(self.owner, self.project, second.pk, True)
        self.assertEqual(second.approvals.get().status, 'pending')
        self.assertEqual(service.balances(self.project)['available'], D('30'))
        self.assertIn('redirect', self.post('receipt_create', {'amount': '100.00', 'received_date': timezone.localdate(), 'comment': 'Дополнительное финансирование'}).json())
        third = self.create_payment(amount='50.00')
        service.submit_payment(self.owner, self.project, third.pk)
        with self.assertRaisesMessage(ValidationError, 'Недостаточно остатка'):
            service.decide_payment(self.owner, self.project, third.pk, True)
        self.assertEqual(third.approvals.get().status, 'pending')
        service.decide_payment(self.owner, self.project, second.pk, True)
        self.assertEqual(service.balances(self.project)['reserved'], D('100'))
        data = budget_data(self.owner, self.project, self.revision)
        for row in [data['rows'][0], data['rows'][1], data['totals']]:
            self.assertEqual(D(row['reserved']), D('100'))
            self.assertEqual(D(row['remaining']), D('0'))
        self.assertEqual(self.post('receipt_create', {'amount': '-1', 'received_date': timezone.localdate(), 'comment': 'Неверно'}).status_code, 422)

    def test_recipient_validation_both_bank_modes_and_invalid_settings(self):
        self.activate(required=True)
        payment = self.create_payment(inn='123 456 789 012')
        payment.refresh_from_db()
        self.assertEqual(payment.inn, '123456789012')
        with self.assertRaises(ValidationError):
            service.submit_payment(self.owner, self.project, payment.pk)
        for fields in [{'inn': '123'}, {'kpp': '123456789'}, {'account': '1'}, {'bik': '123'}, {'correspondent_account': '1'}, {'recipient_type': 'org', 'inn': '1234567890', 'kpp': ''}]:
            form = PaymentForm(self.payment_values(**fields), project=self.project)
            self.assertFalse(form.is_valid(), fields)
        service.save_settings(self.owner, self.project, [self.owner], False)
        service.submit_payment(self.owner, self.project, payment.pk)
        self.project.refresh_from_db()
        partial = self.create_payment(bank_name='Банк')
        service.submit_payment(self.owner, self.project, partial.pk)
        service.save_settings(self.owner, self.project, [], True)
        full = self.create_payment(recipient_type='org', inn='1234567890', kpp='123456789', account='1'*20, bank_name='Банк', bik='1'*9, correspondent_account='2'*20)
        with self.assertRaisesMessage(ValidationError, 'не выбран'):
            service.submit_payment(self.owner, self.project, full.pk)
        with self.assertRaises(ValidationError):
            service.save_settings(self.owner, self.project, [self.editor], True)
        service.save_settings(self.owner, self.project, [self.owner], True)
        service.submit_payment(self.owner, self.project, full.pk)
        self.editor_member.grants.create(code=PP.APPROVE_PAYMENTS)
        service.save_settings(self.owner, self.project, [self.editor], True)
        self.editor_member.grants.all().delete()
        self.assertContains(self.client.get(self.url('budget_settings')), 'Ошибка настройки')

    def test_execution_metadata_file_and_idempotence_audit(self):
        self.activate()
        for key in ['payment_document_date', 'payment_document_number', 'payment_purpose']:
            self.assertEqual(self.post('payment_create', self.payment_values(**{key: 'Недопустимо'})).status_code, 422)
        payment = self.create_payment()
        service.submit_payment(self.owner, self.project, payment.pk)
        service.decide_payment(self.owner, self.project, payment.pk, True)
        values = {'payment_document_date': timezone.localdate(), 'payment_document_number': '0007-A', 'payment_purpose': 'Оплата по счёту №123'}
        self.assertEqual(self.post('payment_execute', {}, payment.pk).status_code, 422)
        self.assertEqual(self.post('payment_execute', {**values, 'payment_document_date': timezone.localdate()+timedelta(days=1)}, payment.pk).status_code, 422)
        self.assertEqual(self.post('payment_execute', values, payment.pk).status_code, 422)
        self.upload(payment)
        self.upload(payment, 'second.pdf')
        self.assertIn('redirect', self.post('payment_execute', values, payment.pk).json())
        self.assertIn('redirect', self.post('payment_execute', values, payment.pk).json())
        payment.refresh_from_db()
        self.assertEqual(payment.payment_document_number, '0007-A')
        self.assertEqual(payment.attachments.count(), 2)
        self.assertEqual(service.balances(self.project)['executed'], D('60'))
        self.assertEqual(service.balances(self.project)['reserved'], D('0'))
        self.assertEqual(AuditEvent.objects.filter(action='payment.executed').count(), 1)
        for audit in AuditEvent.objects.all():
            for sensitive in ['inn', 'kpp', 'account', 'bik', 'recipient_name', 'correspondent_account']:
                self.assertNotIn(sensitive, audit.details)

    def test_project_isolation_files_stages_and_draft_deletion(self):
        self.activate(approvers=[self.owner, self.approver])
        foreign = self.make_project(self.owner)
        foreign_revision = service.ensure_initial(foreign, self.owner)
        foreign_section = BudgetSection.objects.create(revision=foreign_revision, name='Чужая')
        foreign_line = self.make_line(foreign_section)
        event = ProjectEvent.objects.create(project=foreign, title='Чужое мероприятие', start_date=timezone.localdate(), end_date=timezone.localdate(), expected_result='Результат', created_by=self.owner)
        self.assertEqual(self.post('payment_create', self.payment_values(budget_line=str(foreign_line.key))).status_code, 422)
        self.assertEqual(self.post('payment_create', self.payment_values(events=[str(event.pk)])).status_code, 422)
        payment = self.create_payment()
        file = self.upload(payment)
        self.assertEqual(self.get('payment_detail', payment.pk, project=foreign).status_code, 404)
        download = self.url('payment_attachment_download', payment.pk, file.pk)
        response = self.client.get(download)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        response.close()
        self.assertEqual(self.client.get(self.url('payment_attachment_download', payment.pk, file.pk, project=foreign)).status_code, 404)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(download).status_code, 404)
        self.client.force_login(self.approver)
        with self.assertRaises(PermissionDenied):
            service.add_attachment(self.approver, self.project, payment.pk, SimpleUploadedFile('no.pdf', b'no'))
        self.client.force_login(self.owner)
        service.remove_attachment(self.owner, self.project, payment.pk, file.pk)
        service.submit_payment(self.owner, self.project, payment.pk)
        file = service.add_attachment(self.approver, self.project, payment.pk, SimpleUploadedFile('yes.pdf', b'yes'))
        with self.assertRaises(PermissionDenied):
            service.remove_attachment(self.owner, self.project, payment.pk, file.pk)
        with self.assertRaises(PermissionDenied):
            service.delete_payment(self.owner, self.project, payment.pk)
        draft = self.create_payment()
        service.delete_payment(self.owner, self.project, draft.pk)
        next_payment = self.create_payment()
        self.assertGreater(next_payment.number, draft.number)

    def test_json_html_forms_csrf_and_execution_right_is_independent(self):
        self.activate()
        payment = self.create_payment()
        self.assertContains(self.client.get(self.url('project_budget')), 'Общая стоимость')
        self.assertContains(self.client.get(self.url('payment_detail', payment.pk)), 'ИНН')
        self.assertContains(self.client.get(self.url('payment_create')), 'enctype="multipart/form-data"')
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        url = self.url('receipt_create')
        values = {'amount': '10.00', 'received_date': timezone.localdate(), 'comment': 'Поступление'}
        self.assertEqual(client.post(url, values).status_code, 403)
        client.get(url)
        self.assertEqual(client.post(url, values, HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value).status_code, 302)
        service.submit_payment(self.owner, self.project, payment.pk)
        service.decide_payment(self.owner, self.project, payment.pk, True)
        self.editor_member.grants.create(code=PP.EXECUTE_PAYMENTS)
        self.client.force_login(self.editor)
        self.assertEqual(self.get('payment_execute', payment.pk).status_code, 200)
        self.assertEqual(self.get('payment_create').status_code, 403)
        self.assertEqual(self.get('payment_approve', payment.pk).status_code, 403)
        self.assertEqual(self.get('budget_clone').status_code, 403)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        budget_data(self.editor, self.project, self.revision)
        with CaptureQueriesContext(connection) as first_queries:
            budget_data(self.editor, self.project, self.revision)
        self.client.force_login(self.owner)
        for _ in range(3):
            self.create_payment()
        with CaptureQueriesContext(connection) as more_queries:
            budget_data(self.editor, self.project, self.revision)
        self.assertEqual(len(first_queries), len(more_queries))
        self.client.force_login(self.editor)
        self.editor_member.grants.all().delete()
        self.assertEqual(self.get('payment_execute', payment.pk).status_code, 403)
