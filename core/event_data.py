from django.urls import reverse


def event_data(event):
    links = []
    for link in event.indicator_links.all():
        links.append({
            'id': link.pk, 'indicator_id': link.indicator_id,
            'title': link.indicator.title, 'kind': link.indicator.kind, 'unit': link.indicator.unit,
            'planned_value': link.planned_value, 'actual_value': link.actual_value,
            'met': link.actual_value >= link.planned_value if link.actual_value is not None and link.planned_value is not None else None,
        })
    return {
        'id': event.pk, 'title': event.title, 'status': event.status, 'status_label': event.get_status_display(),
        'start_date': event.start_date, 'end_date': event.end_date, 'expected_result': event.expected_result,
        'tasks': event.tasks, 'actual_start_date': event.actual_start_date, 'actual_end_date': event.actual_end_date,
        'actual_result': event.actual_result, 'confirmed_at': event.confirmed_at,
        'confirmed_by': event.confirmed_by.email if event.confirmed_by_id else None,
        'indicators': links,
        'attachments': [{
            'id': attachment.pk, 'name': attachment.original_name, 'kind': attachment.get_kind_display(),
            'size': attachment.size,
            'url': reverse('attachment_download', args=[event.project_id, event.pk, attachment.pk]),
        } for attachment in event.attachments.all()],
    }
