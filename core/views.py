import logging
import uuid
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from .forms import RegistrationForm, EmailAuthenticationForm, RequestForm, ProjectForm, InvitationForm, PermissionForm, SystemGrantForm, DecisionForm, EmailForm
from .models import User, Project, ProjectRequest, ProjectMember, ProjectMemberInvitations, ProjectMemberPermissions, SystemPermissions, AuditEvent
from .permissions import ProjectPermission, SystemPermission, has_project_permission, has_system_permission
from .services import record, send_verification, verification_user, allow_attempt, decide_project_request, set_member_permissions, absolute_url
from .forms import IndicatorForm
from .models import ProjectIndicator
logger = logging.getLogger(__name__)

def render(request, template, context=None, status=200):
    return TemplateResponse(request, template, context or {}, status=status)

def verified_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.email_verified:
            raise PermissionDenied("Подтвердите email.")
        return view(request, *args, **kwargs)
    return wrapped

def system_required(*codes):
    def decorator(view):
        @verified_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not any(has_system_permission(request.user, code) for code in codes):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator

def limited(request, scope, email="", limit=10):
    ip = request.META.get("REMOTE_ADDR", "unknown")
    return allow_attempt(scope + ":ip", ip, limit=limit * 3) and (not email or allow_attempt(scope + ":email", email.strip().lower(), limit=limit))

class LoginView(auth_views.LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = "registration/login.html"
    def post(self, request, *args, **kwargs):
        if not limited(request, "login", request.POST.get("username", "")):
            return HttpResponse("Слишком много попыток входа. Повторите через 15 минут.", status=429)
        return super().post(request, *args, **kwargs)

class PasswordResetView(auth_views.PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")
    def post(self, request, *args, **kwargs):
        if not limited(request, "password_reset", request.POST.get("email", ""), limit=5):
            return HttpResponse("Слишком много запросов. Повторите через 15 минут.", status=429)
        return super().post(request, *args, **kwargs)
    def form_valid(self, form):
        from urllib.parse import urlsplit
        origin = urlsplit(settings.PUBLIC_BASE_URL)
        try:
            form.save(use_https=origin.scheme == "https", domain_override=origin.netloc, from_email=settings.DEFAULT_FROM_EMAIL, email_template_name=self.email_template_name, subject_template_name=self.subject_template_name)
        except Exception:
            logger.exception("Password reset email delivery failed")
        return redirect(self.success_url)

def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if not limited(request, "register", limit=5):
            return HttpResponse("Слишком много регистраций. Повторите через 15 минут.", status=429)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                record(user, "user.registered", user.pk)
            try:
                send_verification(user)
                messages.success(request, "Регистрация завершена. Подтвердите email по ссылке из письма.")
            except Exception:
                logger.exception("Verification email delivery failed")
                messages.error(request, "Аккаунт создан, но письмо не удалось отправить. Запросите его повторно позже.")
            return redirect("resend_verification")
    return render(request, "form.html", {"form": form, "title": "Создайте аккаунт", "subtitle": "Начните работу над своим проектом", "button": "Зарегистрироваться"})

def verify_email(request, token):
    try:
        user = verification_user(token)
    except (signing.BadSignature, User.DoesNotExist, ValueError, KeyError):
        messages.error(request, "Ссылка недействительна или срок ее действия истек.")
        return redirect("resend_verification")
    if request.method == "POST":
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user.pk)
            if user.email_verified:
                messages.info(request, "Email уже подтвержден.")
            else:
                user.email_verified = True
                user.verification_nonce = uuid.uuid4()
                user.save(update_fields=["email_verified", "verification_nonce"])
                record(user, "user.email_verified", user.pk)
                messages.success(request, "Email подтвержден. Теперь можно войти.")
        return redirect("login")
    return render(request, "confirm.html", {"title": "Подтвердите email", "description": user.email, "button": "Подтвердить"})

def resend_verification(request):
    form = EmailForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        if not limited(request, "verify", email, limit=3):
            return HttpResponse("Слишком много запросов. Повторите через 15 минут.", status=429)
        user = User.objects.filter(email__iexact=email, email_verified=False, is_active=True).first()
        if user:
            try:
                send_verification(user)
            except Exception:
                logger.exception("Verification email delivery failed")
        messages.success(request, "Если аккаунт ожидает подтверждения, мы отправили письмо со ссылкой.")
        return redirect("login")
    return render(request, "form.html", {"form": form, "title": "Подтверждение email", "subtitle": "Проверьте почту или запросите новую ссылку", "button": "Отправить письмо"})

def home(request):
    if not request.user.is_authenticated:
        return render(request, "landing.html", {"page": "landing", "title": "Projectus — пространство для ваших проектов"})
    return dashboard(request)

@verified_required
def dashboard(request):
    projects = Project.objects.filter(Q(owner=request.user) | Q(memberships__user=request.user)).distinct()
    return render(request, "dashboard.html", {"projects": projects, "applications": request.user.project_requests.all()})

@verified_required
@require_GET
def my_contracts(request):
    return render(request, "my_contracts.html", {"title": "Мои договоры"})

@verified_required
def request_project(request):
    form = RequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if not limited(request, "project_request", request.user.email, limit=10):
            return HttpResponse("Слишком много заявок. Повторите через 15 минут.", status=429)
        with transaction.atomic():
            application = form.save(commit=False)
            application.applicant = request.user
            application.save()
            record(request.user, "project_request.submitted", application.pk)
        messages.success(request, "Заявка отправлена. Проект появится после одобрения Projectus.")
        return redirect("dashboard")
    return render(request, "form.html", {"form": form, "title": "Новый проект", "subtitle": "Отправьте заявку на создание проекта", "button": "Отправить на рассмотрение"})

def accessible_project(request, pk):
    return get_object_or_404(Project.objects.filter(Q(owner=request.user) | Q(memberships__user=request.user)).distinct(), pk=pk)

def owner_project(request, pk):
    return get_object_or_404(Project, pk=pk, owner=request.user)

@verified_required
def project_detail(request, pk):
    project = accessible_project(request, pk)
    granted = [label for code, label in ProjectPermission.choices if has_project_permission(request.user, project, code)]
    return render(request, "project.html", {"project": project, "owner": project.owner_id == request.user.pk, "can_edit": has_project_permission(request.user, project, ProjectPermission.EDIT_PROJECT), "granted": granted})

@verified_required
@require_GET
def project_indicators(request, pk):
    project = accessible_project(request, pk)
    return render(request, "indicators.html", {
        "project": project, "indicators": project.indicators.all(),
        "can_edit": has_project_permission(request.user, project, ProjectPermission.EDIT_PROJECT),
    })


@verified_required
def indicator_edit(request, pk, indicator_id=None):
    project = accessible_project(request, pk)
    if not has_project_permission(request.user, project, ProjectPermission.EDIT_PROJECT):
        raise PermissionDenied
    indicator = get_object_or_404(project.indicators, pk=indicator_id) if indicator_id else ProjectIndicator(project=project)
    form = IndicatorForm(request.POST if request.method == "POST" else None, instance=indicator)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Event accounting will update current_value independently of these settings.
            indicator = form.save(commit=False)
            indicator.save(update_fields=IndicatorForm.Meta.fields if indicator_id else None)
            record(request.user, "indicator.updated" if indicator_id else "indicator.created", indicator.pk, project=str(project.pk))
        messages.success(request, "Показатель сохранён.")
        return redirect("project_indicators", pk=project.pk)
    return render(request, "form.html", {"project": project, "form": form,
        "title": "Редактирование показателя" if indicator_id else "Новый показатель", "button": "Сохранить показатель"})


@verified_required
@require_GET
def project_section(request, pk, section):
    project = accessible_project(request, pk)
    titles = {
        "indicators": "Показатели",
        "events": "Мероприятия",
        "budget": "Бюджет",
        "contracts": "Договоры",
    }
    return render(request, "project_section.html", {"project": project, "title": titles[section]})

@verified_required
def project_edit(request, pk):
    project = accessible_project(request, pk)
    if not has_project_permission(request.user, project, ProjectPermission.EDIT_PROJECT):
        raise PermissionDenied
    form = ProjectForm(request.POST if request.method == "POST" else None, instance=project)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            record(request.user, "project.updated", project.pk)
        messages.success(request, "Сведения о проекте сохранены.")
        return redirect("project", pk=pk)
    return render(request, "form.html", {"project": project, "form": form, "title": "Сведения о проекте", "button": "Сохранить"})

@verified_required
def members(request, pk):
    project = owner_project(request, pk)
    form = InvitationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if email == request.user.email or project.memberships.filter(user__email=email).exists():
            form.add_error("email", "Пользователь уже имеет доступ к проекту.")
        elif limited(request, "invite", request.user.email, limit=20):
            with transaction.atomic():
                project.invitations.filter(email=email, used_at=None, revoked_at=None).update(revoked_at=timezone.now())
                invitation = ProjectMemberInvitations.objects.create(project=project, email=email, permissions=form.cleaned_data["permissions"], expires_at=timezone.now() + timedelta(days=7))
                record(request.user, "invitation.created", invitation.pk, project=str(project.pk), email=email, permissions=invitation.permissions)
            link = absolute_url(reverse("accept_invitation", args=[invitation.pk]))
            try:
                send_mail("Приглашение в проект — Projectus", f"Вас пригласили в проект «{project.title}». Войдите с email {email} и подтвердите его, если еще не сделали этого, затем примите приглашение (7 дней):\n{link}", settings.DEFAULT_FROM_EMAIL, [email])
                messages.success(request, "Приглашение отправлено.")
            except Exception:
                logger.exception("Invitation delivery failed")
                messages.warning(request, "Приглашение создано, но письмо не отправлено. Скопируйте ссылку из списка приглашений.")
            return redirect("members", pk=pk)
        else:
            return HttpResponse("Слишком много приглашений. Повторите через 15 минут.", status=429)
    pending = project.invitations.filter(used_at=None, revoked_at=None, expires_at__gt=timezone.now())
    return render(request, "members.html", {"project": project, "form": form, "members": project.memberships.select_related("user").prefetch_related("grants"), "invitations": [(inv, absolute_url(reverse("accept_invitation", args=[inv.pk]))) for inv in pending]})

@verified_required
def member_edit(request, pk, member_id):
    project = owner_project(request, pk)
    membership = get_object_or_404(ProjectMember, project=project, pk=member_id)
    form = PermissionForm(request.POST if request.method == "POST" else None, initial={"permissions": list(membership.grants.values_list("code", flat=True))})
    if request.method == "POST" and form.is_valid():
        set_member_permissions(request.user, membership, form.cleaned_data["permissions"])
        messages.success(request, "Права участника сохранены.")
        return redirect("members", pk=pk)
    return render(request, "form.html", {"project": project, "form": form, "title": "Права участника", "subtitle": membership.user.email, "button": "Сохранить права"})

@verified_required
@require_POST
def member_remove(request, pk, member_id):
    project = owner_project(request, pk)
    membership = get_object_or_404(ProjectMember, project=project, pk=member_id)
    with transaction.atomic():
        Project.objects.select_for_update().get(pk=project.pk)
        record(request.user, "member.removed", membership.pk, project=str(pk), email=membership.user.email)
        project.invitations.filter(email=membership.user.email, used_at=None, revoked_at=None).update(revoked_at=timezone.now())
        membership.delete()
    messages.success(request, "Доступ участника отозван.")
    return redirect("members", pk=pk)

@verified_required
@require_POST
def revoke_invitation(request, pk, invitation_id):
    project = owner_project(request, pk)
    with transaction.atomic():
        invitation = get_object_or_404(ProjectMemberInvitations.objects.select_for_update(), pk=invitation_id, project=project)
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])
        record(request.user, "invitation.revoked", invitation.pk, project=str(pk))
    return redirect("members", pk=pk)

@verified_required
def accept_invitation(request, token):
    with transaction.atomic():
        invitation = get_object_or_404(ProjectMemberInvitations.objects.select_for_update().select_related("project"), pk=token)
        if invitation.email != request.user.email:
            raise PermissionDenied("Войдите с email, на который отправлено приглашение.")
        if invitation.used_at or invitation.revoked_at or invitation.expires_at <= timezone.now():
            return render(request, "confirm.html", {"title": "Приглашение недоступно", "description": "Оно уже использовано, отозвано или срок действия истек."}, status=410)
        if request.method == "POST":
            membership, created = ProjectMember.objects.get_or_create(project=invitation.project, user=request.user)
            if created:
                ProjectMemberPermissions.objects.bulk_create([ProjectMemberPermissions(membership=membership, code=code) for code in invitation.permissions])
            invitation.used_at = timezone.now()
            invitation.save(update_fields=["used_at"])
            record(request.user, "invitation.accepted", invitation.pk, project=str(invitation.project_id))
            messages.success(request, "Вы присоединились к проекту.")
            return redirect("project", pk=invitation.project_id)
    return render(request, "confirm.html", {"title": "Приглашение в проект", "description": invitation.project.title, "button": "Присоединиться"})

@system_required(*SystemPermission.values)
def operations(request):
    return render(request, "operations.html", {"can_requests": has_system_permission(request.user, SystemPermission.VIEW_REQUESTS) or has_system_permission(request.user, SystemPermission.APPROVE_PROJECTS), "can_users": has_system_permission(request.user, SystemPermission.VIEW_USERS), "can_audit": has_system_permission(request.user, SystemPermission.VIEW_AUDIT)})

@system_required(SystemPermission.VIEW_REQUESTS, SystemPermission.APPROVE_PROJECTS)
def applications(request):
    from django.core.paginator import Paginator
    return render(request, "applications.html", {"applications": Paginator(ProjectRequest.objects.select_related("applicant", "decided_by"), 30).get_page(request.GET.get("page")), "can_approve": has_system_permission(request.user, SystemPermission.APPROVE_PROJECTS)})

@system_required(SystemPermission.APPROVE_PROJECTS)
def decide_application(request, pk):
    application = get_object_or_404(ProjectRequest, pk=pk)
    form = DecisionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            decide_project_request(request.user, pk, form.cleaned_data["decision"] == "approve", form.cleaned_data["note"])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Решение сохранено.")
            return redirect("applications")
    return render(request, "form.html", {"form": form, "title": application.title, "subtitle": f"{application.applicant.email} — {application.description}", "button": "Сохранить решение"})

@system_required(SystemPermission.VIEW_USERS)
def users(request):
    from django.core.paginator import Paginator
    return render(request, "users.html", {"users": Paginator(User.objects.order_by("email").prefetch_related("system_grants"), 30).get_page(request.GET.get("page"))})

def find_staff_users(query):
    if len("".join(query.split())) < 3 or len(query) > 100:
        return []
    candidates = User.objects.filter(is_active=True, email_verified=True, is_superuser=False)
    for term in query.split():
        candidates = candidates.filter(Q(email__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term))
    return list(candidates.only("id", "email", "first_name", "last_name").order_by("email")[:11])

@verified_required
@require_GET
def staff_user_search(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    query = request.GET.get("q", "").strip()
    if len(query) > 100:
        return JsonResponse({"error": "Введите не более 100 символов."}, status=400)
    matches = find_staff_users(query)
    return JsonResponse({
        "results": [{"id": user.pk, "email": user.email, "name": user.get_full_name()} for user in matches[:10]],
        "has_more": len(matches) > 10,
    })

@verified_required
def staff_permissions(request):
    from django.core.paginator import Paginator
    if not request.user.is_superuser:
        raise PermissionDenied
    eligible = User.objects.filter(is_active=True, email_verified=True, is_superuser=False)
    employee = None
    initial = {}
    if request.method == "GET" and request.GET.get("user_id"):
        try:
            user_id = SystemGrantForm.base_fields["user_id"].clean(request.GET["user_id"])
        except ValidationError:
            raise Http404
        employee = get_object_or_404(eligible, pk=user_id)
        initial = {"user_id": employee.pk, "permissions": list(employee.system_grants.values_list("code", flat=True))}
    form = SystemGrantForm(request.POST if request.method == "POST" else None, initial=initial)
    if request.method == "POST":
        valid = form.is_valid()
        employee = eligible.filter(pk=form.cleaned_data.get("user_id")).first()
        if valid:
            with transaction.atomic():
                target = eligible.select_for_update().filter(pk=form.cleaned_data["user_id"]).first()
                if not target:
                    form.add_error("user_id", "Выберите активного пользователя с подтвержденным email. Главному аккаунту полномочия не назначаются.")
                else:
                    previous = list(target.system_grants.values_list("code", flat=True))
                    target.system_grants.all().delete()
                    SystemPermissions.objects.bulk_create([SystemPermissions(user=target, code=code) for code in form.cleaned_data["permissions"]])
                    record(request.user, "system.permissions_changed", target.pk, before=previous, after=form.cleaned_data["permissions"])
            if target:
                messages.success(request, "Полномочия сохранены. Пустой список отзывает все полномочия.")
                return redirect("staff_permissions")
    staff = eligible.filter(system_grants__isnull=False).distinct().order_by("email").prefetch_related("system_grants")
    query = request.GET.get("q", "").strip()
    matches = find_staff_users(query) if request.method == "GET" and not employee else []
    return render(request, "staff_permissions.html", {
        "form": form, "selected_user": employee,
        "staff": Paginator(staff, 30).get_page(request.GET.get("page")),
        "search_query": query, "search_results": matches[:10], "search_has_more": len(matches) > 10,
    })

@system_required(SystemPermission.VIEW_AUDIT)
def audit(request):
    from django.core.paginator import Paginator
    return render(request, "audit.html", {"events": Paginator(AuditEvent.objects.select_related("actor"), 50).get_page(request.GET.get("page"))})
