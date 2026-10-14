from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from . import tests as existing
from .models import ProjectIndicator, ProjectMember, ProjectMemberPermissions, Project, ProjectRequest, AuditEvent
from .permissions import ProjectPermission


class IndicatorTests(TestCase):
    setUp = existing.ProjectusTests.setUp
    project = existing.ProjectusTests.project
    sign_in = existing.ProjectusTests.sign_in

    def post(self, url, data):
        return self.client.post(url, data, HTTP_ACCEPT='application/json')

    def get(self, url):
        return self.client.get(url, HTTP_ACCEPT='application/json')

    def test_create_edit_and_progress(self):
        project = self.project()
        self.sign_in(self.owner)
        url = reverse('indicator_create', args=[project.pk])
        kind = next(f for f in self.get(url).json()['data']['form']['fields'] if f['name'] == 'kind')
        self.assertEqual(kind['value'], 'qualitative')
        values = {'kind': 'quantitative', 'title': 'Количество участников', 'target_value': '20.5', 'unit': 'чел.', 'current_value': '999'}
        response = self.post(url, values)
        self.assertEqual(response.status_code, 200)
        indicator = project.indicators.get()
        self.assertEqual(indicator.current_value, 0)
        self.assertEqual(indicator.target_value, Decimal('20.5'))
        list_url = response.json()['redirect']
        data = self.get(list_url).json()['data']
        self.assertEqual(data['indicators'][0]['progress_percent'], '0.0')
        self.assertTrue(data['can_edit'])
        # Simulate the future event accounting layer; ordinary edits cannot overwrite its total.
        indicator.current_value = Decimal('25.625')
        indicator.save(update_fields=['current_value'])
        edit = reverse('indicator_edit', args=[project.pk, indicator.pk])
        self.assertIn('redirect', self.post(edit, {**values, 'target_value': '10.25', 'current_value': '0'}).json())
        indicator.refresh_from_db()
        self.assertEqual(indicator.current_value, Decimal('25.625'))
        self.assertEqual(indicator.progress_percent, Decimal('250.0'))
        self.assertEqual(self.get(list_url).json()['data']['indicators'][0]['progress_percent'], '250.0')
        html = self.client.get(list_url)
        self.assertContains(html, 'Количество участников')
        self.assertContains(html, 'Цель достигнута')
        self.assertTrue(AuditEvent.objects.filter(action='indicator.created', target=str(indicator.pk)).exists())
        self.assertTrue(AuditEvent.objects.filter(action='indicator.updated', target=str(indicator.pk)).exists())

    def test_qualitative_result_and_type_locked_on_edit(self):
        project = self.project()
        self.sign_in(self.owner)
        values = {'kind': 'qualitative', 'title': 'Улучшение навыков', 'result': 'Участники освоили основы', 'achieved': 'on'}
        self.post(reverse('indicator_create', args=[project.pk]), values)
        indicator = project.indicators.get()
        self.assertIsNone(indicator.target_value)
        self.assertTrue(indicator.achieved)
        self.assertIsNone(indicator.progress_percent)
        edit = reverse('indicator_edit', args=[project.pk, indicator.pk])
        response = self.post(edit, {**values, 'kind': 'quantitative', 'target_value': '10', 'achieved': ''})
        self.assertIn('redirect', response.json())
        indicator.refresh_from_db()
        self.assertEqual(indicator.kind, 'qualitative')
        self.assertIsNone(indicator.target_value)
        self.assertFalse(indicator.achieved)
        self.assertEqual(indicator.result, values['result'])

    def test_validation_and_database_constraints(self):
        project = self.project()
        self.sign_in(self.owner)
        url = reverse('indicator_create', args=[project.pk])
        for value in ['', '0', '-1', 'nan', '1.0001', '1000000000000']:
            with self.subTest(value=value):
                response = self.post(url, {'kind': 'quantitative', 'title': 'Участники', 'target_value': value})
                self.assertEqual(response.status_code, 422)
                self.assertTrue(next(f for f in response.json()['data']['form']['fields'] if f['name'] == 'target_value')['errors'])
        for values in [{'kind': 'invalid', 'title': 'Описание'}, {'kind': 'qualitative', 'title': '  '}]:
            self.assertEqual(self.post(url, values).status_code, 422)
        self.assertEqual(project.indicators.count(), 0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectIndicator.objects.create(project=project, title='Invalid', kind='quantitative', target_value=0)

    def test_permissions_and_project_isolation(self):
        project = self.project()
        list_url = reverse('project_indicators', args=[project.pk])
        create = reverse('indicator_create', args=[project.pk])
        indicator = project.indicators.create(title='Первый', kind='qualitative')
        edit = reverse('indicator_edit', args=[project.pk, indicator.pk])
        self.assertEqual(self.get(list_url).status_code, 401)
        for user in [self.other, self.root]:
            self.sign_in(user)
            self.assertEqual(self.get(list_url).status_code, 404)
            self.assertEqual(self.post(create, {'kind': 'qualitative', 'title': 'Запрещено'}).status_code, 404)
        member = ProjectMember.objects.create(project=project, user=self.other)
        self.sign_in(self.other)
        self.assertFalse(self.get(list_url).json()['data']['can_edit'])
        self.assertEqual(self.get(create).status_code, 403)
        self.assertEqual(self.post(edit, {'title': 'Запрещено'}).status_code, 403)
        grant = ProjectMemberPermissions.objects.create(membership=member, code=ProjectPermission.EDIT_PROJECT)
        self.assertIn('redirect', self.post(create, {'kind': 'qualitative', 'title': 'Разрешено'}).json())
        self.assertIn('redirect', self.post(edit, {'title': 'Обновлено'}).json())
        request = ProjectRequest.objects.create(applicant=self.owner, title='Другой проект')
        other_project = Project.objects.create(owner=self.owner, request=request, title=request.title)
        other_indicator = other_project.indicators.create(title='Чужой', kind='qualitative')
        self.assertEqual(self.post(reverse('indicator_edit', args=[project.pk, other_indicator.pk]), {'title': 'Подмена'}).status_code, 404)
        grant.delete()
        self.assertEqual(self.post(edit, {'title': 'Отозвано'}).status_code, 403)
        self.assertEqual(self.post(list_url, {}).status_code, 405)
