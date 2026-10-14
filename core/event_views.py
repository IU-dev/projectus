from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .event_forms import EventPlanForm, EventResultForm, EventAttachmentForm
from .event_services import confirm_event
from .models import ProjectEvent, EventIndicator, EventAttachment
from .permissions import ProjectPermission as PP, has_project_permission
from .services import record
from .views import verified_required, accessible_project, render


def event_permissions(user, project):
    return {
        'can_plan': has_project_permission(user, project, PP.EDIT_EVENTS),
        'can_record': has_project_permission(user, project, PP.EDIT_EVENT_RESULTS),
        'can_confirm': has_project_permission(user, project, PP.CONFIRM_EVENTS),
    }


def viewable_project(request, pk):
    project = accessible_project(request, pk)
    if not (has_project_permission(request.user, project, PP.VIEW_EVENTS) or any(event_permissions(request.user, project).values())):
        raise PermissionDenied
    return project


def event_query(project):
    return project.project_events.select_related('confirmed_by').prefetch_related('indicator_links__indicator', 'attachments')


@verified_required
@require_GET
def event_list(request, pk):
    project = viewable_project(request, pk)
    return render(request, 'events.html', {'project': project, 'project_events': event_query(project), **event_permissions(request.user, project)})


@verified_required
@require_GET
def event_detail(request, pk, event_id):
    project = viewable_project(request, pk)
    event = get_object_or_404(event_query(project), pk=event_id)
    permissions = event_permissions(request.user, project)
    form = EventAttachmentForm() if permissions['can_record'] and event.status == ProjectEvent.Status.CONDUCTED else None
    return render(request, 'event_detail.html', {'project': project, 'event': event, 'form': form, **permissions})


@verified_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def event_plan(request, pk, event_id=None):
    project = viewable_project(request, pk)
    if not has_project_permission(request.user, project, PP.EDIT_EVENTS):
        raise PermissionDenied
    event = get_object_or_404(project.project_events.select_for_update(), pk=event_id) if event_id else ProjectEvent(project=project, created_by=request.user)
    if event.status == ProjectEvent.Status.CONFIRMED:
        raise PermissionDenied('Подтверждённое мероприятие нельзя редактировать.')
    form = EventPlanForm(request.POST if request.method == 'POST' else None, instance=event, project=project)
    if request.method == 'POST' and form.is_valid():
        event = form.save()
        selected = form.cleaned_data['indicators']
        event.indicator_links.exclude(indicator_id__in=selected).delete()
        for item in form.project_indicators:
            if str(item.pk) in selected:
                EventIndicator.objects.update_or_create(event=event, indicator=item, defaults={'planned_value': form.cleaned_data.get(f'planned_{item.pk}')})
        record(request.user, 'event.plan_updated' if event_id else 'event.created', event.pk, project=str(project.pk))
        messages.success(request, 'План мероприятия сохранён.')
        return redirect('event_detail', pk=project.pk, event_id=event.pk)
    return render(request, 'form.html', {'project': project, 'form': form, 'title': 'План мероприятия' if event_id else 'Новое мероприятие', 'button': 'Сохранить план'})


@verified_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def event_result(request, pk, event_id):
    project = viewable_project(request, pk)
    if not has_project_permission(request.user, project, PP.EDIT_EVENT_RESULTS):
        raise PermissionDenied
    event = get_object_or_404(project.project_events.select_for_update(), pk=event_id)
    if event.status == ProjectEvent.Status.CONFIRMED:
        raise PermissionDenied('Подтверждённое мероприятие нельзя редактировать.')
    form = EventResultForm(request.POST if request.method == 'POST' else None, instance=event)
    if request.method == 'POST' and form.is_valid():
        event = form.save(commit=False)
        event.status = ProjectEvent.Status.CONDUCTED
        event.save(update_fields=[*EventResultForm.Meta.fields, 'status'])
        for link in form.links:
            if link.indicator.kind == 'quantitative':
                link.actual_value = form.cleaned_data[f'actual_{link.indicator_id}']
                link.save(update_fields=['actual_value'])
        record(request.user, 'event.results_updated', event.pk, project=str(project.pk))
        messages.success(request, 'Фактические результаты сохранены. Проведение ожидает подтверждения.')
        return redirect('event_detail', pk=project.pk, event_id=event.pk)
    return render(request, 'form.html', {'project': project, 'form': form, 'title': 'Факт проведения мероприятия', 'button': 'Сохранить факт проведения'})


@verified_required
@require_http_methods(['GET', 'POST'])
def event_confirm(request, pk, event_id):
    project = viewable_project(request, pk)
    if not has_project_permission(request.user, project, PP.CONFIRM_EVENTS):
        raise PermissionDenied
    event = get_object_or_404(project.project_events, pk=event_id)
    description = f'Подтвердить проведение «{event.title}»? Фактические показатели будут учтены в проекте. После подтверждения изменение мероприятия и вложений станет недоступно.'
    status = 200
    if request.method == 'POST':
        try:
            confirm_event(request.user, project, event_id)
        except ValidationError as exc:
            description = ' '.join(exc.messages)
            status = 422
        else:
            messages.success(request, 'Проведение мероприятия подтверждено.')
            return redirect('event_detail', pk=project.pk, event_id=event.pk)
    return render(request, 'confirm.html', {'project': project, 'title': 'Подтверждение проведения', 'description': description, 'button': 'Подтвердить проведение' if event.status == ProjectEvent.Status.CONDUCTED else None}, status=status)


@verified_required
@require_http_methods(['GET', 'POST'])
def attachment_upload(request, pk, event_id):
    project = viewable_project(request, pk)
    if not has_project_permission(request.user, project, PP.EDIT_EVENT_RESULTS):
        raise PermissionDenied
    attachment = None
    try:
        with transaction.atomic():
            event = get_object_or_404(project.project_events.select_for_update(), pk=event_id)
            if event.status != ProjectEvent.Status.CONDUCTED:
                raise PermissionDenied('Вложения доступны только до подтверждения проведённого мероприятия.')
            if request.method == 'GET':
                return redirect('event_detail', pk=project.pk, event_id=event.pk)
            form = EventAttachmentForm(request.POST, request.FILES)
            if form.is_valid():
                file = form.cleaned_data['file']
                attachment = EventAttachment(event=event, kind=form.cleaned_data['kind'], file=file,
                    original_name=Path(file.name.replace('\\', '/')).name[:255], size=file.size, uploaded_by=request.user)
                attachment.save()
                record(request.user, 'event.attachment_added', attachment.pk, event=str(event.pk), project=str(project.pk))
                messages.success(request, 'Файл прикреплён.')
                return redirect('event_detail', pk=project.pk, event_id=event.pk)
            return render(request, 'event_detail.html', {'page': 'event_detail', 'project': project, 'event': event,
                'form': form, **event_permissions(request.user, project)}, status=422)
    except Exception:
        if attachment is not None and attachment.file and attachment.file._committed:
            attachment.file.delete(save=False)
        raise


@verified_required
@require_POST
@transaction.atomic
def attachment_remove(request, pk, event_id, attachment_id):
    project = viewable_project(request, pk)
    if not has_project_permission(request.user, project, PP.EDIT_EVENT_RESULTS):
        raise PermissionDenied
    event = get_object_or_404(project.project_events.select_for_update(), pk=event_id)
    if event.status != ProjectEvent.Status.CONDUCTED:
        raise PermissionDenied
    attachment = get_object_or_404(event.attachments, pk=attachment_id)
    storage, name = attachment.file.storage, attachment.file.name
    attachment.delete()
    transaction.on_commit(lambda: storage.delete(name))
    record(request.user, 'event.attachment_removed', attachment_id, event=str(event.pk), project=str(project.pk))
    return redirect('event_detail', pk=project.pk, event_id=event.pk)


@verified_required
@require_GET
def attachment_download(request, pk, event_id, attachment_id):
    project = viewable_project(request, pk)
    attachment = get_object_or_404(EventAttachment, pk=attachment_id, event_id=event_id, event__project=project)
    try:
        file = attachment.file.open('rb')
    except FileNotFoundError:
        raise Http404
    response = FileResponse(file, as_attachment=True, filename=attachment.original_name, content_type='application/octet-stream')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
