from django.test import TestCase
from django.urls import reverse

from .models import AuditEvent, SystemPermissions, User
from .permissions import SystemPermission as SP


class StaffPermissionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser('root@example.com', 'VeryStrongPass!241')
        cls.employee = User.objects.create_user(
            'employee@example.com', email_verified=True, first_name='Anna', last_name='Petrova',
        )
        cls.inactive = User.objects.create_user('inactive@example.com', is_active=False, email_verified=True)
        cls.unverified = User.objects.create_user('unverified@example.com')

    def get(self, route, **params):
        return self.client.get(reverse(route), params, HTTP_ACCEPT='application/json')

    def post(self, data):
        return self.client.post(reverse('staff_permissions'), data, HTTP_ACCEPT='application/json')

    def test_search_is_bounded_and_matches_name_or_email(self):
        self.client.force_login(self.root)
        for query in ['', 'an', 'a  n']:
            self.assertEqual(self.get('staff_user_search', q=query).json(), {'results': [], 'has_more': False})
        for query in ['EMPLOYEE', 'anna', 'petrova', 'Petrova Anna']:
            response = self.get('staff_user_search', q=query)
            self.assertEqual(response.json()['results'], [
                {'id': self.employee.pk, 'email': self.employee.email, 'name': 'Anna Petrova'},
            ])
            self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(self.get('staff_user_search', q='example.com').json()['results'][0]['id'], self.employee.pk)
        self.assertEqual(len(self.get('staff_user_search', q='example.com').json()['results']), 1)
        self.assertEqual(self.get('staff_user_search', q='x' * 101).status_code, 400)
        User.objects.bulk_create([User(email=f'match{i:02}@example.com', email_verified=True) for i in range(12)])
        payload = self.get('staff_user_search', q='match').json()
        self.assertEqual(len(payload['results']), 10)
        self.assertTrue(payload['has_more'])
        self.assertEqual(payload['results'][0]['email'], 'match00@example.com')

    def test_search_and_grants_require_verified_superuser(self):
        self.assertEqual(self.get('staff_user_search', q='employee').status_code, 401)
        SystemPermissions.objects.create(user=self.employee, code=SP.VIEW_USERS)
        for user in [self.employee, self.unverified]:
            self.client.force_login(user)
            self.assertEqual(self.get('staff_user_search', q='employee').status_code, 403)
            self.assertEqual(self.get('staff_permissions', user_id=self.employee.pk).status_code, 403)
            self.assertEqual(self.post({'user_id': self.employee.pk, 'permissions': [SP.VIEW_AUDIT]}).status_code, 403)
        self.assertFalse(AuditEvent.objects.filter(action='system.permissions_changed').exists())

    def test_selection_loads_grants_and_invalid_targets_cannot_change_them(self):
        self.client.force_login(self.root)
        SystemPermissions.objects.create(user=self.employee, code=SP.VIEW_AUDIT)
        payload = self.get('staff_permissions', user_id=self.employee.pk).json()['data']
        self.assertEqual(payload['selected_user']['id'], self.employee.pk)
        fields = {field['name']: field for field in payload['form']['fields']}
        self.assertEqual(fields['user_id']['kind'], 'hidden')
        self.assertEqual(fields['permissions']['value'], [SP.VIEW_AUDIT])
        for user_id in ['', 'invalid', 2**64, 999999, self.root.pk, self.inactive.pk, self.unverified.pk]:
            with self.subTest(user_id=user_id):
                self.assertEqual(self.post({'user_id': user_id, 'permissions': [SP.VIEW_USERS]}).status_code, 422)
        self.assertEqual(self.post({'user_id': self.employee.pk, 'permissions': ['unknown']}).status_code, 422)
        self.assertEqual(list(self.employee.system_grants.values_list('code', flat=True)), [SP.VIEW_AUDIT])
        self.employee.is_active = False
        self.employee.save(update_fields=['is_active'])
        self.assertEqual(self.post({'user_id': self.employee.pk}).status_code, 422)
        self.assertTrue(self.employee.system_grants.exists())
        self.assertFalse(AuditEvent.objects.filter(action='system.permissions_changed').exists())
