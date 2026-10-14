from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from . import tests as existing
from .models import Project, ProjectMember, ProjectMemberInvitations, SystemPermissions
from .permissions import ProjectPermission as PP, SystemPermission as SP


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class FrontendTests(TestCase):
    # Reuse fixture helpers while testing the same routes through the JSON API.
    setUp = existing.ProjectusTests.setUp
    project = existing.ProjectusTests.project
    sign_in = existing.ProjectusTests.sign_in
    def api_get(self, url, **kwargs):
        return self.client.get(url, HTTP_ACCEPT='application/json', **kwargs)

    def api_post(self, url, data=None):
        return self.client.post(url, data or {}, HTTP_ACCEPT='application/json')

    def test_project_information_roundtrip_and_validation(self):
        project = self.project()
        self.sign_in(self.owner)
        url = reverse('project_edit', args=[project.pk])
        values = {'title': project.title, 'description': 'Кратко о проекте',
                  'goals': [' Первая цель ', '', 'Вторая цель'], 'tasks': ['Задача 1', 'Задача 2'],
                  'start_date': '2026-10-01', 'end_date': '2026-12-31'}
        self.assertIn('redirect', self.api_post(url, values).json())
        project.refresh_from_db()
        self.assertEqual(project.goals, ['Первая цель', 'Вторая цель'])
        self.assertEqual(project.tasks, ['Задача 1', 'Задача 2'])
        data = self.api_get(reverse('project', args=[project.pk])).json()['data']['project']
        self.assertEqual(data['start_date'], '2026-10-01')
        self.assertEqual(data['goals'], project.goals)
        fields = {f['name']: f for f in self.api_get(url).json()['data']['form']['fields']}
        self.assertEqual(fields['goals']['value'], ['Первая цель', 'Вторая цель'])
        self.assertEqual(fields['goals']['kind'], 'text-list')
        self.assertEqual(fields['end_date']['value'], '2026-12-31')
        self.assertEqual(fields['end_date']['kind'], 'date')
        html = self.client.get(reverse('project', args=[project.pk]))
        self.assertContains(html, 'Вторая цель')
        self.assertNotContains(html, 'Ваш доступ')
        for invalid in ['2026-09-30', 'invalid']:
            response = self.api_post(url, {**values, 'end_date': invalid})
            self.assertEqual(response.status_code, 422)
            self.assertTrue(next(f for f in response.json()['data']['form']['fields'] if f['name'] == 'end_date')['errors'])
            project.refresh_from_db()
            self.assertEqual(project.end_date.isoformat(), '2026-12-31')
        self.assertIn('redirect', self.api_post(url, {**values, 'end_date': values['start_date']}).json())
        self.assertIn('redirect', self.api_post(url, {'title': project.title, 'goals': '', 'tasks': '', 'start_date': '', 'end_date': ''}).json())
        project.refresh_from_db()
        self.assertEqual(project.goals, [])
        self.assertEqual(project.tasks, [])
        self.assertIsNone(project.start_date)
        self.assertIsNone(project.end_date)

    def test_vue_shell_and_private_json_envelope(self):
        self.sign_in(self.owner)
        self.assertContains(self.client.get('/'), 'projectus-bootstrap')
        response = self.api_get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['page'], 'dashboard')
        self.assertEqual(response.json()['user']['email'], self.owner.email)
        self.assertIn('Accept', response['Vary'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        for secret in ['verification_nonce', 'password', 'last_login']:
            self.assertNotIn(secret, response.json()['user'])

    def test_home_shows_landing_only_to_guests(self):
        project = self.project()
        response = self.api_get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['page'], 'landing')
        self.assertIsNone(response.json()['user'])
        self.assertNotIn('projects', response.json()['data'])
        self.assertNotContains(self.client.get('/'), project.title)
        self.assertContains(self.client.get('/'), 'Начать работу')
        self.sign_in(self.owner)
        response = self.api_get('/')
        self.assertEqual(response.json()['page'], 'dashboard')
        self.assertEqual(response.json()['data']['projects'][0]['id'], str(project.pk))
        self.owner.email_verified = False
        self.owner.save(update_fields=['email_verified'])
        self.assertEqual(self.api_get('/').status_code, 403)

    def test_my_contracts_available_without_project_access(self):
        url = reverse('my_contracts')
        self.assertEqual(self.api_get(url).status_code, 401)
        self.sign_in(self.other)
        response = self.api_get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['page'], 'my_contracts')
        self.assertNotIn('project', response.json()['data'])
        self.assertContains(self.client.get(url), 'Мои договоры')
        self.assertEqual(self.api_post(url).status_code, 405)
        self.other.email_verified = False
        self.other.save(update_fields=['email_verified'])
        self.assertEqual(self.api_get(url).status_code, 403)

    def test_json_login_registration_validation_and_logout(self):
        response = self.api_post('/register/', {'email': 'new@example.com', 'password1': 'VeryStrongPass!241', 'password2': 'VeryStrongPass!241'})
        self.assertEqual(response.json()['redirect'], '/email/resend/')
        self.assertEqual(len(mail.outbox), 1)
        denied = self.api_post('/login/', {'username': 'new@example.com', 'password': 'VeryStrongPass!241'})
        self.assertEqual(denied.status_code, 422)
        self.assertTrue(denied.json()['data']['form']['errors'])
        password = next(f for f in denied.json()['data']['form']['fields'] if f['name'] == 'password')
        self.assertEqual(password['value'], '')
        response = self.api_post('/login/?next=/projects/request/', {'username': self.owner.email, 'password': 'VeryStrongPass!241', 'next': '/projects/request/'})
        self.assertEqual(response.json()['redirect'], '/projects/request/')
        self.assertTrue(response.json()['csrf_token'])
        self.assertEqual(self.api_post('/logout/').json()['redirect'], '/login/')
        self.assertEqual(self.api_get('/projects/request/').status_code, 401)

    def test_json_isolation_and_grants_checked_on_every_mutation(self):
        project = self.project()
        for user in [self.other, self.root]:
            self.sign_in(user)
            for route in ['project', 'project_edit', 'members']:
                self.assertEqual(self.api_get(reverse(route, args=[project.pk])).status_code, 404)
        member = ProjectMember.objects.create(project=project, user=self.other)
        self.sign_in(self.other)
        edit = reverse('project_edit', args=[project.pk])
        self.assertEqual(self.api_post(edit, {'title': 'hacked'}).status_code, 403)
        self.sign_in(self.owner)
        permissions = reverse('member_edit', args=[project.pk, member.pk])
        self.api_post(permissions, {'permissions': [PP.EDIT_PROJECT]})
        self.sign_in(self.other)
        self.assertEqual(self.api_post(edit, {'title': 'Updated', 'owner': self.other.pk}).json()['redirect'], reverse('project', args=[project.pk]))
        project.refresh_from_db()
        self.assertEqual(project.owner, self.owner)
        self.sign_in(self.owner)
        self.api_post(permissions, {})
        self.sign_in(self.other)
        self.assertEqual(self.api_post(edit, {'title': 'hacked'}).status_code, 403)

    def test_json_invitation_requires_registered_recipient(self):
        project = self.project()
        self.sign_in(self.owner)
        members = reverse('members', args=[project.pk])
        response = self.api_post(members, {'email': 'not-registered@example.com'})
        self.assertEqual(response.status_code, 422)
        email_field = next(field for field in response.json()['data']['form']['fields'] if field['name'] == 'email')
        self.assertIn('Сначала нужна регистрация в Projectus.', email_field['errors'][0])
        self.assertFalse(ProjectMemberInvitations.objects.exists())
        self.assertEqual(len(mail.outbox), 0)
        response = self.api_post(members, {'email': self.other.email.upper(), 'permissions': [PP.EDIT_PROJECT]})
        self.assertEqual(response.json()['redirect'], members)
        self.assertEqual(len(mail.outbox), 1)
        invitation = ProjectMemberInvitations.objects.get(email=self.other.email)
        self.sign_in(self.other)
        accept = reverse('accept_invitation', args=[invitation.pk])
        self.assertEqual(self.api_get(accept).json()['page'], 'accept_invitation')
        self.assertEqual(ProjectMember.objects.count(), 0)
        self.assertEqual(self.api_post(accept).json()['redirect'], reverse('project', args=[project.pk]))
        self.assertEqual(self.api_post(accept).status_code, 410)

    def test_project_sections_require_project_access(self):
        project = self.project()
        routes = ['project_indicators', 'project_events', 'project_budget', 'project_contracts']
        for route in routes:
            url = reverse(route, args=[project.pk])
            self.assertEqual(self.api_get(url).status_code, 401)
        for account in [self.other, self.root]:
            self.sign_in(account)
            for route in routes:
                self.assertEqual(self.api_get(reverse(route, args=[project.pk])).status_code, 404)
        member = ProjectMember.objects.create(project=project, user=self.other)
        self.sign_in(self.other)
        self.assertEqual(self.api_get(reverse('project_events', args=[project.pk])).status_code, 403)
        member.grants.create(code=PP.VIEW_EVENTS)
        self.assertEqual(self.api_get(reverse('project_budget', args=[project.pk])).status_code, 403)
        member.grants.create(code=PP.VIEW_FINANCE)
        for route in routes:
            url = reverse(route, args=[project.pk])
            response = self.api_get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['data']['project']['id'], str(project.pk))
            self.assertEqual(self.api_post(url).status_code, 405)
        self.assertContains(self.client.get(reverse(routes[0], args=[project.pk])), 'projectus-bootstrap')
        member.delete()
        self.assertEqual(self.api_get(reverse(routes[0], args=[project.pk])).status_code, 404)

    def test_project_forms_keep_project_context(self):
        project = self.project()
        member = ProjectMember.objects.create(project=project, user=self.other)
        self.sign_in(self.owner)
        for route, args in [('project_edit', [project.pk]), ('member_edit', [project.pk, member.pk])]:
            data = self.api_get(reverse(route, args=args)).json()['data']
            self.assertEqual(data['project']['id'], str(project.pk))
        response = self.api_post(reverse('project_edit', args=[project.pk]), {'title': ''})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['data']['project']['id'], str(project.pk))

    def test_json_system_access_and_decisions(self):
        SystemPermissions.objects.create(user=self.staff, code=SP.VIEW_REQUESTS)
        self.sign_in(self.staff)
        self.assertEqual(self.api_get('/operations/applications/').status_code, 200)
        decision = reverse('decide_application', args=[self.application.pk])
        for url in ['/operations/users/', '/operations/audit/', '/operations/staff/']:
            self.assertEqual(self.api_get(url).status_code, 403)
        self.assertEqual(self.api_post(decision, {'decision': 'approve'}).status_code, 403)
        self.sign_in(self.root)
        decision_page = self.api_get(decision).json()
        self.assertEqual(next(f for f in decision_page['data']['form']['fields'] if f['name'] == 'decision')['value'], 'approve')
        self.assertEqual(self.api_post(decision, {'decision': 'reject'}).status_code, 422)
        self.assertEqual(Project.objects.count(), 0)
        self.assertEqual(self.api_post(decision, {'decision': 'approve'}).json()['redirect'], '/operations/applications/')
        self.assertEqual(self.api_post(decision, {'decision': 'approve'}).status_code, 422)
        self.assertEqual(Project.objects.count(), 1)

    def test_json_csrf_rotation_and_post_only_actions(self):
        client = Client(enforce_csrf_checks=True)
        initial = client.get('/login/', HTTP_ACCEPT='application/json').json()['csrf_token']
        response = client.post('/login/', {'username': self.owner.email, 'password': 'VeryStrongPass!241'}, HTTP_ACCEPT='application/json', HTTP_X_CSRFTOKEN=initial)
        current = response.json()['csrf_token']
        self.assertNotEqual(initial, current)
        self.assertEqual(client.post('/projects/request/', {'title': 'No CSRF'}, HTTP_ACCEPT='application/json').status_code, 403)
        self.assertEqual(client.post('/projects/request/', {'title': 'Stale CSRF'}, HTTP_ACCEPT='application/json', HTTP_X_CSRFTOKEN=initial).status_code, 403)
        self.assertEqual(client.post('/projects/request/', {'title': 'Good CSRF'}, HTTP_ACCEPT='application/json', HTTP_X_CSRFTOKEN=current).status_code, 200)
        self.assertEqual(client.get('/logout/', HTTP_ACCEPT='application/json').status_code, 405)
        self.assertEqual(client.put('/projects/request/', HTTP_ACCEPT='application/json', HTTP_X_CSRFTOKEN=current).status_code, 405)

    def test_json_password_reset_confirm_and_session_invalidation(self):
        self.sign_in(self.owner)
        self.assertEqual(self.api_post('/password/reset/', {'email': self.owner.email}).json()['redirect'], '/password/reset/sent/')
        self.assertEqual(len(mail.outbox), 1)
        url = reverse('password_reset_confirm', args=[urlsafe_base64_encode(force_bytes(self.owner.pk)), default_token_generator.make_token(self.owner)])
        reset_client = Client()
        safe_url = reset_client.get(url, HTTP_ACCEPT='application/json').json()['redirect']
        page = reset_client.get(safe_url, HTTP_ACCEPT='application/json').json()
        self.assertTrue(page['data']['validlink'])
        response = reset_client.post(safe_url, {'new_password1': 'AnotherStrongPass!398', 'new_password2': 'AnotherStrongPass!398'}, HTTP_ACCEPT='application/json')
        self.assertEqual(response.json()['redirect'], '/password/reset/complete/')
        self.assertEqual(self.api_get('/projects/request/').status_code, 401)

    def test_json_pagination_invalid_empty_forms_and_html_bootstrap_escape(self):
        self.sign_in(self.root)
        page = self.api_get('/operations/users/?page=999').json()
        self.assertEqual(page['data']['pagination']['page'], 1)
        self.sign_in(self.owner)
        self.assertEqual(self.api_post('/projects/request/').status_code, 422)
        project = self.project()
        project.title = '</script><script>alert(1)</script>'
        project.save()
        html = self.client.get('/')
        self.assertNotContains(html, project.title)
        self.assertContains(html, '\\u003C/script\\u003E')
