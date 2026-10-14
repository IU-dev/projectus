import hashlib
from datetime import timedelta
from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from .models import AuditEvent, RateLimit, ProjectRequest, Project, ProjectMember, ProjectMemberPermissions
from .permissions import SystemPermission, has_system_permission

def record(actor, action, target, **details):
    AuditEvent.objects.create(actor=actor, action=action, target=str(target), details=details)

def absolute_url(path):
    return settings.PUBLIC_BASE_URL.rstrip("/") + path

def send_verification(user):
    token = signing.dumps({"user": user.pk, "nonce": str(user.verification_nonce)}, salt="verify-email")
    send_mail("Подтвердите email — Projectus", "Подтвердите email по ссылке (действует 24 часа):\n" + absolute_url(reverse("verify_email", args=[token])), settings.DEFAULT_FROM_EMAIL, [user.email])

def verification_user(token):
    from .models import User
    data = signing.loads(token, salt="verify-email", max_age=86400)
    return User.objects.get(pk=data["user"], verification_nonce=data["nonce"], is_active=True)

def allow_attempt(scope, identifier, limit=10, seconds=900):
    key = hashlib.sha256(f"{scope}:{identifier}".encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        RateLimit.objects.get_or_create(key=key, defaults={"started_at": now})
        bucket = RateLimit.objects.select_for_update().get(key=key)
        if bucket.started_at + timedelta(seconds=seconds) <= now:
            bucket.started_at = now
            bucket.count = 0
        if bucket.count >= limit:
            return False
        bucket.count += 1
        bucket.save(update_fields=["count", "started_at"])
        return True

@transaction.atomic
def decide_project_request(actor, pk, approve, note=""):
    if not has_system_permission(actor, SystemPermission.APPROVE_PROJECTS):
        raise PermissionDenied
    application = ProjectRequest.objects.select_for_update().get(pk=pk)
    if application.status != ProjectRequest.Status.PENDING:
        raise ValidationError("Заявка уже рассмотрена.")
    application.status = ProjectRequest.Status.APPROVED if approve else ProjectRequest.Status.REJECTED
    application.decided_by = actor
    application.decided_at = timezone.now()
    application.decision_note = note
    application.save()
    if approve:
        Project.objects.create(owner=application.applicant, request=application, title=application.title, description=application.description)
    record(actor, "project_request.approved" if approve else "project_request.rejected", application.pk, note=note)
    return application

@transaction.atomic
def set_member_permissions(actor, membership, codes):
    Project.objects.select_for_update().get(pk=membership.project_id)
    if membership.project.owner_id != actor.pk:
        raise PermissionDenied
    previous = list(membership.grants.values_list("code", flat=True))
    membership.grants.all().delete()
    ProjectMemberPermissions.objects.bulk_create([ProjectMemberPermissions(membership=membership, code=code) for code in codes])
    record(actor, "member.permissions_changed", membership.pk, project=str(membership.project_id), before=previous, after=codes)
