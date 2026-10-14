from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import ProjectEvent, ProjectIndicator, EventIndicator
from .permissions import ProjectPermission, has_project_permission
from .services import record


@transaction.atomic
def confirm_event(actor, project, event_id):
    if not has_project_permission(actor, project, ProjectPermission.CONFIRM_EVENTS):
        raise PermissionDenied
    event = ProjectEvent.objects.select_for_update().get(project=project, pk=event_id)
    if event.status == ProjectEvent.Status.CONFIRMED:
        return event
    if event.status != ProjectEvent.Status.CONDUCTED:
        raise ValidationError('Сначала внесите фактические результаты мероприятия.')
    links = list(event.indicator_links.select_related('indicator'))
    quantities = [link for link in links if link.indicator.kind == ProjectIndicator.Kind.QUANTITATIVE]
    if any(link.actual_value is None for link in quantities):
        raise ValidationError('Укажите фактическое значение каждого количественного показателя.')
    # Lock indicators in a stable order: confirmations of different events may overlap.
    indicators = list(ProjectIndicator.objects.select_for_update().filter(pk__in=[link.indicator_id for link in quantities]).order_by('pk'))
    event.status = ProjectEvent.Status.CONFIRMED
    event.confirmed_by = actor
    event.confirmed_at = timezone.now()
    event.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])
    for indicator in indicators:
        total = EventIndicator.objects.filter(indicator=indicator, event__status=ProjectEvent.Status.CONFIRMED).aggregate(total=Sum('actual_value'))['total'] or Decimal('0')
        if total > Decimal('999999999999.999'):
            raise ValidationError('Суммарное значение показателя превышает допустимый предел.')
        indicator.current_value = total
        indicator.save(update_fields=['current_value'])
    record(actor, 'event.confirmed', event.pk, project=str(project.pk))
    return event
