from django.db import models
class ProjectPermission(models.TextChoices):
    EDIT_PROJECT = "edit_project", "Изменять сведения проекта"
    VIEW_EVENTS = "view_events", "Просматривать мероприятия"
    EDIT_EVENTS = "edit_events", "Создавать и редактировать плановые мероприятия"
    EDIT_EVENT_RESULTS = "edit_event_results", "Вносить и редактировать результаты мероприятий"
    CONFIRM_EVENTS = "confirm_events", "Подтверждать проведение мероприятий"
    VIEW_FINANCE = "view_finance", "Просматривать финансы"
    EDIT_BUDGET = "edit_budget", "Редактировать смету и лимиты"
    PREPARE_PAYMENTS = "prepare_payments", "Планировать и учитывать платежи"
    APPROVE_PAYMENTS = "approve_payments", "Согласовывать платежи"
    APPROVE_BUDGET_CHANGES = "approve_budget_changes", "Согласовывать изменения сметы и переносы"
    EXECUTE_PAYMENTS = "execute_payments", "Исполнять согласованные платежи"
    RECORD_RECEIPTS = "record_receipts", "Отражать поступления средств"
    VIEW_CONTRACTS = "view_contracts", "Просматривать договоры"
    EDIT_CONTRACTS = "edit_contracts", "Подготавливать договоры и акты"
    SIGN_CONTRACTS = "sign_contracts", "Подписывать договоры и акты"
    VIEW_GRANTS = "view_grants", "Просматривать заявки на поддержку"
    EDIT_GRANTS = "edit_grants", "Вести заявки на поддержку"
class SystemPermission(models.TextChoices):
    VIEW_REQUESTS = "view_requests", "Просматривать заявки на создание проектов"
    APPROVE_PROJECTS = "approve_projects", "Одобрять и отклонять заявки"
    VIEW_USERS = "view_users", "Просматривать пользователей"
    VIEW_AUDIT = "view_audit", "Просматривать журнал действий"
def has_system_permission(user, code):
    return user.is_authenticated and user.is_active and user.email_verified and (user.is_superuser or user.system_grants.filter(code=code).exists())
def has_project_permission(user, project, code):
    if not user.is_authenticated or not user.is_active or not user.email_verified:
        return False
    return project.owner_id == user.pk or project.memberships.filter(user=user, grants__code=code).exists()
