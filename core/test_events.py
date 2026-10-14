from datetime import date
from decimal import Decimal
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from . import tests as existing
from .models import Project, ProjectRequest, ProjectMember, ProjectMemberPermissions, ProjectEvent, EventIndicator, EventAttachment, AuditEvent
from .permissions import ProjectPermission as PP


class EventTests(TestCase):
    project = existing.ProjectusTests.project
    sign_in = existing.ProjectusTests.sign_in

    def setUp(self):
        existing.ProjectusTests.setUp(self)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.media = override_settings(MEDIA_ROOT=self.directory.name)
        self.media.enable()
        self.addCleanup(self.media.disable)
        self.p = self.project()
        self.p.tasks = ['Подготовить площадку', 'Пригласить участников']
        self.p.save()
        self.quantity = self.p.indicators.create(title='Участники', kind='quantitative', target_value=10, unit='чел.')
        self.quality = self.p.indicators.create(title='Навыки общения', kind='qualitative')
        self.sign_in(self.owner)

    def url(self, route, event=None, attachment=None):
        args = [self.p.pk]
        if event:
            args.append(event.pk)
        if attachment:
            args.append(attachment.pk)
        return reverse(route, args=args)

    def post(self, url, data=None):
        return self.client.post(url, data or {}, HTTP_ACCEPT='application/json')

    def get(self, url):
        return self.client.get(url, HTTP_ACCEPT='application/json')

    def plan(self, **changes):
        return {'title': 'Мастер-класс', 'start_date': '2025-01-10', 'end_date': '2025-01-11',
                'expected_result': 'Участники освоят основы', 'tasks': self.p.tasks,
                'indicators': [str(self.quantity.pk), str(self.quality.pk)], f'planned_{self.quantity.pk}': '8', **changes}

    def create_event(self):
        response = self.post(self.url('event_create'), self.plan())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('redirect', response.json())
        return self.p.project_events.latest('pk')

    def results(self, **changes):
        return {'actual_start_date': '2025-01-10', 'actual_end_date': '2025-01-12', 'actual_result': 'Провели мастер-класс', f'actual_{self.quantity.pk}': '6.5', **changes}

    def conduct(self, event, **changes):
        response = self.post(self.url('event_result', event), self.results(**changes))
        self.assertIn('redirect', response.json(), response.content)
        event.refresh_from_db()

    def test_plan_actual_confirmation_and_aggregate(self):
        event = self.create_event()
        self.assertEqual(event.tasks, self.p.tasks)
        self.assertEqual(event.indicator_links.count(), 2)
        self.assertIsNone(event.indicator_links.get(indicator=self.quality).planned_value)
        self.assertEqual(self.post(self.url('event_confirm', event)).status_code, 422)
        self.conduct(event)
        self.quantity.refresh_from_db()
        self.assertEqual(self.quantity.current_value, 0)
        detail = self.get(self.url('event_detail', event)).json()['data']['event']
        self.assertEqual(detail['status'], 'conducted')
        self.assertFalse(next(item for item in detail['indicators'] if item['kind'] == 'quantitative')['met'])
        self.conduct(event, **{f'actual_{self.quantity.pk}': '9.25'})
        for _ in range(2):
            self.assertIn('redirect', self.post(self.url('event_confirm', event)).json())
        self.quantity.refresh_from_db()
        self.assertEqual(self.quantity.current_value, Decimal('9.25'))
        self.assertEqual(AuditEvent.objects.filter(action='event.confirmed', target=str(event.pk)).count(), 1)
        event.refresh_from_db()
        self.assertEqual(event.confirmed_by, self.owner)
        self.assertIsNotNone(event.confirmed_at)
        other = self.create_event()
        self.conduct(other, **{f'actual_{self.quantity.pk}': '2'})
        self.post(self.url('event_confirm', other))
        self.quantity.refresh_from_db()
        self.quality.refresh_from_db()
        self.assertEqual(self.quantity.current_value, Decimal('11.25'))
        self.assertEqual(self.quantity.progress_percent, Decimal('112.5'))
        self.assertFalse(self.quality.achieved)
        self.assertContains(self.client.get(self.url('event_detail', event)), 'План выполнен')

    def test_confirmed_event_is_immutable_including_files(self):
        event = self.create_event()
        self.conduct(event)
        self.post(self.url('attachment_upload', event), {'file': SimpleUploadedFile('list.txt', b'evidence')})
        attachment = event.attachments.get()
        self.post(self.url('event_confirm', event))
        for route, payload in [('event_plan', self.plan(title='Changed')), ('event_result', self.results(actual_result='Changed')),
                               ('attachment_upload', {'file': SimpleUploadedFile('new.txt', b'new')})]:
            self.assertEqual(self.post(self.url(route, event), payload).status_code, 403)
        self.assertEqual(self.post(self.url('attachment_remove', event, attachment)).status_code, 403)
        event.refresh_from_db()
        self.assertEqual(event.title, 'Мастер-класс')
        self.assertEqual(event.actual_result, 'Провели мастер-класс')
        self.assertEqual(event.attachments.count(), 1)
        self.assertEqual(self.client.get(self.url('attachment_download', event, attachment)).status_code, 200)

    def test_three_permissions_are_independent_and_revocable(self):
        event = self.create_event()
        member = ProjectMember.objects.create(project=self.p, user=self.other)
        self.sign_in(self.other)
        self.assertEqual(self.get(self.url('project_events')).status_code, 403)
        for permission in [PP.VIEW_EVENTS, PP.EDIT_EVENTS, PP.EDIT_EVENT_RESULTS, PP.CONFIRM_EVENTS]:
            member.grants.all().delete()
            member.grants.create(code=permission)
            self.assertEqual(self.get(self.url('project_events')).status_code, 200)
            self.assertEqual(self.get(self.url('event_plan', event)).status_code, 200 if permission == PP.EDIT_EVENTS else 403)
            self.assertEqual(self.get(self.url('event_result', event)).status_code, 200 if permission == PP.EDIT_EVENT_RESULTS else 403)
            self.assertEqual(self.get(self.url('event_confirm', event)).status_code, 200 if permission == PP.CONFIRM_EVENTS else 403)
            if permission != PP.EDIT_EVENTS:
                self.assertEqual(self.post(self.url('event_create'), self.plan()).status_code, 403)
            if permission != PP.EDIT_EVENT_RESULTS:
                self.assertEqual(self.post(self.url('event_result', event), self.results()).status_code, 403)
            if permission != PP.CONFIRM_EVENTS:
                self.assertEqual(self.post(self.url('event_confirm', event)).status_code, 403)
        member.grants.all().delete()
        self.assertEqual(self.post(self.url('event_result', event), self.results()).status_code, 403)
        for user in [self.staff, self.root]:
            self.sign_in(user)
            self.assertEqual(self.get(self.url('project_events')).status_code, 404)
        self.client.logout()
        self.assertEqual(self.get(self.url('project_events')).status_code, 401)

    def test_foreign_links_and_invalid_dates_values_are_rejected(self):
        request = ProjectRequest.objects.create(applicant=self.owner, title='Другой')
        other = Project.objects.create(owner=self.owner, request=request, title='Другой')
        indicator = other.indicators.create(title='Чужой', kind='quantitative', target_value=1)
        for changes in [{'tasks': ['Чужая задача']}, {'indicators': [str(indicator.pk)]}, {'end_date': '2025-01-01'},
                        {f'planned_{self.quantity.pk}': ''}, {f'planned_{self.quantity.pk}': '-1'}, {f'planned_{self.quantity.pk}': '1.0001'}]:
            self.assertEqual(self.post(self.url('event_create'), self.plan(**changes)).status_code, 422)
        event = self.create_event()
        for changes in [{'actual_result': ' '}, {'actual_end_date': '2025-01-01'}, {'actual_end_date': '2999-01-01'},
                        {f'actual_{self.quantity.pk}': ''}, {f'actual_{self.quantity.pk}': '-1'}]:
            self.assertEqual(self.post(self.url('event_result', event), self.results(**changes)).status_code, 422)
        event.refresh_from_db()
        self.assertEqual(event.status, 'planned')
        self.assertEqual(self.post(reverse('event_result', args=[other.pk, event.pk]), self.results()).status_code, 404)
        self.conduct(event, **{f'actual_{self.quantity.pk}': '0'})
        self.assertEqual(event.indicator_links.get(indicator=self.quantity).actual_value, 0)
        self.assertIn('redirect', self.post(self.url('event_confirm', event)).json())

    def test_plan_updates_preserve_actual_and_require_new_facts(self):
        event = self.create_event()
        self.conduct(event)
        self.assertEqual(self.post(self.url('event_plan', event), self.plan(indicators=[])).status_code, 422)
        extra = self.p.indicators.create(title='События', kind='quantitative', target_value=5)
        response = self.post(self.url('event_plan', event), self.plan(indicators=[str(self.quantity.pk), str(extra.pk)], **{f'planned_{extra.pk}': '1'}))
        self.assertIn('redirect', response.json())
        self.assertEqual(event.indicator_links.get(indicator=self.quantity).actual_value, Decimal('6.5'))
        self.assertEqual(self.post(self.url('event_confirm', event)).status_code, 422)
        self.conduct(event, **{f'actual_{extra.pk}': '1'})
        self.assertIn('redirect', self.post(self.url('event_confirm', event)).json())

    def test_private_upload_download_remove_and_limits(self):
        event = self.create_event()
        upload = self.url('attachment_upload', event)
        self.assertEqual(self.post(upload, {'file': SimpleUploadedFile('a.txt', b'test')}).status_code, 403)
        self.conduct(event)
        self.assertEqual(self.post(upload, {}).status_code, 422)
        self.assertEqual(self.post(upload, {'kind': 'invalid', 'file': SimpleUploadedFile('a.txt', b'a')}).status_code, 422)
        large = SimpleUploadedFile('large.bin', b'x' * (20 * 1024 * 1024 + 1))
        self.assertEqual(self.post(upload, {'file': large}).status_code, 422)
        self.assertIn('redirect', self.post(upload, {'file': SimpleUploadedFile('../participants.txt', b'evidence')}).json())
        attachment = event.attachments.get()
        self.assertEqual(attachment.kind, 'other')
        self.assertEqual(attachment.original_name, 'participants.txt')
        download = self.url('attachment_download', event, attachment)
        response = self.client.get(download)
        self.assertEqual(b''.join(response.streaming_content), b'evidence')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.sign_in(self.other)
        self.assertEqual(self.client.get(download).status_code, 404)
        member = ProjectMember.objects.create(project=self.p, user=self.other)
        self.assertEqual(self.client.get(download).status_code, 403)
        member.grants.create(code=PP.VIEW_EVENTS)
        self.assertEqual(self.client.get(download).status_code, 200)
        self.assertEqual(self.post(self.url('attachment_remove', event, attachment)).status_code, 403)
        self.sign_in(self.owner)
        storage, name = attachment.file.storage, attachment.file.name
        with self.captureOnCommitCallbacks(execute=True):
            self.assertIn('redirect', self.post(self.url('attachment_remove', event, attachment)).json())
        self.assertFalse(storage.exists(name))
        self.assertEqual(self.client.get(download).status_code, 404)

    def test_event_mutations_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        event = self.create_event()
        for route in ['event_create', 'event_plan', 'event_result', 'event_confirm', 'attachment_upload']:
            url = self.url(route, None if route == 'event_create' else event)
            self.assertEqual(client.post(url, {}, HTTP_ACCEPT='application/json').status_code, 403)

    def test_sum_overflow_rolls_back_confirmation(self):
        event = self.create_event()
        self.conduct(event, **{f'actual_{self.quantity.pk}': '999999999999.999'})
        self.post(self.url('event_confirm', event))
        other = self.create_event()
        self.conduct(other, **{f'actual_{self.quantity.pk}': '1'})
        self.assertEqual(self.post(self.url('event_confirm', other)).status_code, 422)
        other.refresh_from_db()
        self.assertEqual(other.status, 'conducted')
        self.assertIsNone(other.confirmed_at)
