import re
from datetime import timedelta
from django.contrib.auth.tokens import default_token_generator
from django.core import mail, signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import User, ProjectRequest, Project, ProjectMember, ProjectMemberPermissions, SystemPermissions, ProjectMemberInvitations, AuditEvent
from .permissions import ProjectPermission as PP, SystemPermission as SP, has_project_permission, has_system_permission
from .services import decide_project_request, send_verification, allow_attempt

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ProjectusTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner@example.com', 'VeryStrongPass!241', email_verified=True)
        self.other = User.objects.create_user('other@example.com', 'VeryStrongPass!241', email_verified=True)
        self.staff = User.objects.create_user('staff@example.com', 'VeryStrongPass!241', email_verified=True)
        self.root = User.objects.create_superuser('root@example.com', 'VeryStrongPass!241')
        self.application = ProjectRequest.objects.create(applicant=self.owner, title='Социальный проект', description='Помощь людям')

    def project(self):
        decide_project_request(self.root, self.application.pk, True)
        return Project.objects.get(request=self.application)

    def sign_in(self, user):
        self.client.force_login(user)

    def invite(self, project, **kwargs):
        return ProjectMemberInvitations.objects.create(project=project, email=self.other.email, permissions=[PP.EDIT_PROJECT], expires_at=timezone.now()+timedelta(days=7), **kwargs)

    def test_registration_verification_login(self):
        response = self.client.post(reverse('register'), {'email':'New@EXAMPLE.com', 'first_name':'Анна', 'password1':'VeryStrongPass!241', 'password2':'VeryStrongPass!241'})
        self.assertRedirects(response, reverse('resend_verification'))
        user = User.objects.get(email='new@example.com')
        self.assertTrue(user.check_password('VeryStrongPass!241'))
        self.assertFalse(user.email_verified)
        response = self.client.post(reverse('login'), {'username':user.email, 'password':'VeryStrongPass!241'})
        self.assertContains(response, 'Подтвердите email')
        url = re.search(r'http://127.0.0.1:8000([^\s]+)', mail.outbox[0].body)[1]
        self.assertEqual(self.client.get(url).status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)
        self.assertRedirects(self.client.post(url), reverse('login'))
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertRedirects(self.client.post(reverse('login'), {'username':'NEW@EXAMPLE.COM', 'password':'VeryStrongPass!241'}), reverse('dashboard'))
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_case_insensitive_email_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('OWNER@EXAMPLE.COM', 'password')

    def test_duplicate_registration_and_weak_password(self):
        response = self.client.post(reverse('register'), {'email':'OWNER@example.com','password1':'123','password2':'123'})
        self.assertContains(response, 'Этот email уже зарегистрирован')
        self.assertEqual(User.objects.count(), 4)

    def test_invalid_and_expired_verification(self):
        self.assertRedirects(self.client.post(reverse('verify_email', args=['bad-token'])), reverse('resend_verification'))
        user = User.objects.create_user('unverified@example.com', 'VeryStrongPass!241')
        token = signing.dumps({'user': user.pk, 'nonce':str(user.verification_nonce)}, salt='verify-email')
        from unittest.mock import patch
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp()+90000):
            self.assertEqual(self.client.post(reverse('verify_email', args=[token])).status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_verification_resend_generic_response(self):
        user = User.objects.create_user('unverified@example.com', 'VeryStrongPass!241')
        self.client.post(reverse('resend_verification'), {'email': user.email})
        self.assertEqual(len(mail.outbox), 1)
        self.client.post(reverse('resend_verification'), {'email': 'missing@example.com'})
        self.assertEqual(len(mail.outbox), 1)

    def test_login_throttled(self):
        for _ in range(10):
            self.client.post(reverse('login'), {'username':self.owner.email, 'password':'wrong'})
        self.assertEqual(self.client.post(reverse('login'), {'username':self.owner.email, 'password':'wrong'}).status_code, 429)

    def test_rate_limit_expires(self):
        self.assertTrue(allow_attempt('test', 'x', limit=1, seconds=0))
        self.assertTrue(allow_attempt('test', 'x', limit=1, seconds=0))
        self.assertTrue(allow_attempt('other', 'x', limit=1))
        self.assertFalse(allow_attempt('other', 'x', limit=1))

    @override_settings(ALLOWED_HOSTS=["testserver", "hostile.example"])
    def test_password_reset_and_session_invalidation(self):
        self.sign_in(self.owner)
        response = self.client.post(reverse('password_reset'), {'email': self.owner.email}, HTTP_HOST='hostile.example')
        self.assertEqual(response.status_code, 302)
        self.assertIn('http://127.0.0.1:8000/', mail.outbox[0].body)
        self.assertNotIn('hostile.example', mail.outbox[0].body)
        url = reverse('password_reset_confirm', args=[urlsafe_base64_encode(force_bytes(self.owner.pk)), default_token_generator.make_token(self.owner)])
        reset_client = Client()
        response = reset_client.get(url)
        reset_url = response.url
        self.assertEqual(reset_client.get(reset_url).status_code, 200)
        response = reset_client.post(reset_url, {'new_password1':'AnotherStrongPass!398', 'new_password2':'AnotherStrongPass!398'})
        self.assertRedirects(response, reverse('password_reset_complete'))
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password('AnotherStrongPass!398'))
        self.assertEqual(self.client.get(reverse('request_project')).status_code, 302)

    def test_no_project_before_approval(self):
        self.sign_in(self.owner)
        self.assertRedirects(self.client.post(reverse('request_project'), {'title':'Новый проект', 'description':'Описание'}), reverse('dashboard'))
        self.assertEqual(ProjectRequest.objects.count(), 2)
        self.assertEqual(Project.objects.count(), 0)
        self.assertContains(self.client.get(reverse('dashboard')), 'На рассмотрении')

    def test_approval_creates_owned_project_once(self):
        project = self.project()
        self.assertEqual(project.owner, self.owner)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'approved')
        with self.assertRaises(ValidationError):
            decide_project_request(self.root, self.application.pk, True)
        self.assertEqual(Project.objects.count(), 1)

    def test_unauthorized_approval_service(self):
        with self.assertRaises(PermissionDenied):
            decide_project_request(self.owner, self.application.pk, True)
        self.assertEqual(Project.objects.count(), 0)

    def test_individual_system_permissions(self):
        SystemPermissions.objects.create(user=self.staff, code=SP.APPROVE_PROJECTS)
        self.sign_in(self.staff)
        self.assertEqual(self.client.get(reverse('applications')).status_code, 200)
        self.assertEqual(self.client.get(reverse('users')).status_code, 403)
        self.assertEqual(self.client.get(reverse('audit')).status_code, 403)
        self.assertEqual(self.client.get(reverse('staff_permissions')).status_code, 403)
        self.assertRedirects(self.client.post(reverse('decide_application', args=[self.application.pk]), {'decision':'approve'}), reverse('applications'))
        self.assertEqual(Project.objects.count(), 1)

    def test_request_viewer_cannot_approve(self):
        SystemPermissions.objects.create(user=self.staff, code=SP.VIEW_REQUESTS)
        self.sign_in(self.staff)
        self.assertEqual(self.client.get(reverse('applications')).status_code, 200)
        self.assertEqual(self.client.post(reverse('decide_application', args=[self.application.pk]), {'decision':'approve'}).status_code, 403)
        self.assertEqual(Project.objects.count(), 0)

    def test_rejection_requires_note_and_creates_no_project(self):
        self.sign_in(self.root)
        url = reverse('decide_application', args=[self.application.pk])
        self.assertContains(self.client.post(url, {'decision':'reject','note':''}), 'Укажите причину')
        self.client.post(url, {'decision':'reject','note':'Уточните цели'})
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'rejected')
        self.assertEqual(Project.objects.count(), 0)

    def test_stranger_and_system_admin_cannot_access_client_project(self):
        project = self.project()
        for account in [self.other, self.root]:
            self.sign_in(account)
            self.assertNotContains(self.client.get(reverse('dashboard')), project.title)
            for route in ['project', 'project_edit', 'members']:
                self.assertEqual(self.client.get(reverse(route, args=[project.pk])).status_code, 404)

    def test_member_cannot_edit_without_permission(self):
        project = self.project()
        ProjectMember.objects.create(project=project, user=self.other)
        self.sign_in(self.other)
        self.assertEqual(self.client.get(reverse('project', args=[project.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse('project_edit', args=[project.pk]), {'title':'hacked'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('members', args=[project.pk])).status_code, 404)
        self.assertFalse(has_project_permission(self.other, project, PP.VIEW_FINANCE))

    def test_member_can_edit_only_after_explicit_grant(self):
        project = self.project()
        member = ProjectMember.objects.create(project=project, user=self.other)
        ProjectMemberPermissions.objects.create(membership=member, code=PP.EDIT_PROJECT)
        self.sign_in(self.other)
        self.assertRedirects(self.client.post(reverse('project_edit', args=[project.pk]), {'title':'Изменено','description':'Описание','owner':self.other.pk}), reverse('project', args=[project.pk]))
        project.refresh_from_db()
        self.assertEqual(project.title, 'Изменено')
        self.assertEqual(project.owner, self.owner)
        self.assertTrue(has_project_permission(self.other, project, PP.EDIT_PROJECT))
        self.assertFalse(has_project_permission(self.other, project, PP.APPROVE_PAYMENTS))

    def test_owner_updates_and_revokes_member_permissions(self):
        project = self.project()
        member = ProjectMember.objects.create(project=project, user=self.other)
        self.sign_in(self.owner)
        url = reverse('member_edit', args=[project.pk, member.pk])
        self.client.post(url, {'permissions':[PP.VIEW_FINANCE, PP.PREPARE_PAYMENTS]})
        self.assertTrue(has_project_permission(self.other, project, PP.PREPARE_PAYMENTS))
        self.assertFalse(has_project_permission(self.other, project, PP.APPROVE_PAYMENTS))
        self.client.post(url, {})
        self.assertFalse(member.grants.exists())
        self.assertEqual(AuditEvent.objects.filter(action='member.permissions_changed').count(), 2)

    def test_unknown_permission_rejected(self):
        project = self.project()
        member = ProjectMember.objects.create(project=project, user=self.other)
        self.sign_in(self.owner)
        response = self.client.post(reverse('member_edit', args=[project.pk, member.pk]), {'permissions':['become_superuser']})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(member.grants.exists())

    def test_invitation_delivery_and_accept_once(self):
        project = self.project()
        self.sign_in(self.owner)
        self.assertRedirects(self.client.post(reverse('members', args=[project.pk]), {'email':'OTHER@example.com','permissions':[PP.EDIT_PROJECT]}), reverse('members', args=[project.pk]))
        invitation = ProjectMemberInvitations.objects.get()
        self.assertIn(reverse('accept_invitation', args=[invitation.pk]), mail.outbox[0].body)
        self.assertFalse(ProjectMember.objects.exists())
        self.sign_in(self.other)
        url = reverse('accept_invitation', args=[invitation.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertFalse(ProjectMember.objects.exists())
        self.assertRedirects(self.client.post(url), reverse('project', args=[project.pk]))
        self.assertTrue(has_project_permission(self.other, project, PP.EDIT_PROJECT))
        self.assertEqual(self.client.post(url).status_code, 410)

    def test_invitation_rejects_unregistered_email_without_changing_old_invite(self):
        project = self.project()
        invitation = self.invite(project)
        invitation.email = 'not-registered@example.com'
        invitation.save(update_fields=['email'])
        self.sign_in(self.owner)
        response = self.client.post(reverse('members', args=[project.pk]), {'email': invitation.email})
        self.assertContains(response, 'Сначала нужна регистрация в Projectus.')
        self.assertEqual(ProjectMemberInvitations.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)
        invitation.refresh_from_db()
        self.assertIsNone(invitation.revoked_at)

    def test_invitation_bound_to_email(self):
        project = self.project()
        invitation = self.invite(project)
        self.sign_in(self.staff)
        self.assertEqual(self.client.post(reverse('accept_invitation', args=[invitation.pk])).status_code, 403)
        self.assertFalse(ProjectMember.objects.exists())

    def test_invitation_expired_and_revoked(self):
        project = self.project()
        invitation = self.invite(project)
        self.sign_in(self.other)
        url = reverse('accept_invitation', args=[invitation.pk])
        invitation.expires_at = timezone.now()-timedelta(seconds=1)
        invitation.save()
        self.assertEqual(self.client.post(url).status_code, 410)
        invitation.expires_at = timezone.now()+timedelta(days=1)
        invitation.revoked_at = timezone.now()
        invitation.save()
        self.assertEqual(self.client.post(url).status_code, 410)
        self.assertFalse(ProjectMember.objects.exists())

    def test_membership_removal_prevents_reentry(self):
        project = self.project()
        member = ProjectMember.objects.create(project=project, user=self.other)
        invitation = self.invite(project)
        self.sign_in(self.owner)
        self.client.post(reverse('member_remove', args=[project.pk, member.pk]))
        self.sign_in(self.other)
        self.assertEqual(self.client.get(reverse('project', args=[project.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('accept_invitation', args=[invitation.pk])).status_code, 410)

    def test_only_owner_can_revoke_invite(self):
        project = self.project()
        invitation = self.invite(project)
        self.sign_in(self.other)
        self.assertEqual(self.client.post(reverse('revoke_invitation', args=[project.pk, invitation.pk])).status_code, 404)
        self.sign_in(self.owner)
        self.client.post(reverse('revoke_invitation', args=[project.pk, invitation.pk]))
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.revoked_at)

    def test_root_grants_and_revokes_system_permissions(self):
        self.sign_in(self.root)
        self.client.post(reverse('staff_permissions'), {'user_id':self.staff.pk,'permissions':[SP.VIEW_AUDIT]})
        self.assertTrue(has_system_permission(self.staff, SP.VIEW_AUDIT))
        self.assertFalse(has_system_permission(self.staff, SP.APPROVE_PROJECTS))
        self.assertContains(self.client.get(reverse('staff_permissions'), {'user_id': self.staff.pk}), 'checked')
        self.client.post(reverse('staff_permissions'), {'user_id':self.staff.pk})
        self.assertFalse(has_system_permission(self.staff, SP.VIEW_AUDIT))
        self.assertEqual(AuditEvent.objects.filter(action='system.permissions_changed').count(), 2)

    def test_unverified_user_denied_even_with_session_and_grants(self):
        self.owner.email_verified = False
        self.owner.save()
        self.sign_in(self.owner)
        SystemPermissions.objects.create(user=self.owner, code=SP.APPROVE_PROJECTS)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 403)
        self.assertFalse(has_system_permission(self.owner, SP.APPROVE_PROJECTS))

    def test_csrf_and_post_required(self):
        project = self.project()
        member = ProjectMember.objects.create(project=project, user=self.other)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(reverse('member_remove', args=[project.pk, member.pk])).status_code, 403)
        self.sign_in(self.owner)
        self.assertEqual(self.client.get(reverse('member_remove', args=[project.pk, member.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertTrue(ProjectMember.objects.filter(pk=member.pk).exists())

    def test_xss_escaped(self):
        project = self.project()
        project.title = '<script>alert(1)</script>'
        project.save()
        self.sign_in(self.owner)
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;')

    def test_all_main_pages_render(self):
        project = self.project()
        self.sign_in(self.root)
        for name in ['operations','applications','users','staff_permissions','audit','password_change']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.sign_in(self.owner)
        for name in ['dashboard','request_project']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for name in ['project','project_edit','members']:
            self.assertEqual(self.client.get(reverse(name,args=[project.pk])).status_code, 200, name)
