from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import ProjectEvent, ProjectIndicator, EventAttachment


class EventPlanForm(forms.ModelForm):
    tasks = forms.MultipleChoiceField(label="Задачи проекта", required=False, widget=forms.CheckboxSelectMultiple)
    indicators = forms.MultipleChoiceField(label="Показатели проекта", required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = ProjectEvent
        fields = ['title', 'start_date', 'end_date', 'expected_result', 'tasks']
        widgets = {name: forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}) for name in ['start_date', 'end_date']}

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_indicators = list(project.indicators.all())
        task_choices = list(dict.fromkeys([*project.tasks, *(self.instance.tasks or [])]))
        self.fields['tasks'].choices = [(task, task) for task in task_choices]
        self.fields['tasks'].help_text = 'Выбранные формулировки сохраняются в плане мероприятия.'
        self.fields['indicators'].choices = [(str(item.pk), item.title) for item in self.project_indicators]
        links = {link.indicator_id: link for link in self.instance.indicator_links.all()} if self.instance.pk else {}
        self.initial['indicators'] = [str(pk) for pk in links]
        for item in self.project_indicators:
            if item.kind == ProjectIndicator.Kind.QUANTITATIVE:
                field = f'planned_{item.pk}'
                self.fields[field] = forms.DecimalField(label=f'План: {item.title}', required=False, min_value=Decimal('0'), max_digits=15, decimal_places=3, help_text=item.unit)
                self.fields[field].show_when = {'field': 'indicators', 'value': str(item.pk)}
                if item.pk in links:
                    self.initial[field] = links[item.pk].planned_value

    def clean(self):
        data = super().clean()
        if data.get('start_date') and data.get('end_date') and data['end_date'] < data['start_date']:
            self.add_error('end_date', 'Дата окончания не может быть раньше даты начала.')
        for item in self.project_indicators:
            field = f'planned_{item.pk}'
            if str(item.pk) in data.get('indicators', []) and field in self.fields and data.get(field) is None and field not in self.errors:
                self.add_error(field, 'Укажите плановое значение, в том числе ноль.')
        if self.instance.pk and 'indicators' in data:
            if self.instance.indicator_links.filter(actual_value__isnull=False).exclude(indicator_id__in=data['indicators']).exists():
                self.add_error('indicators', 'Нельзя отвязать показатель, по которому уже внесён фактический результат.')
        return data


class EventResultForm(forms.ModelForm):
    class Meta:
        model = ProjectEvent
        fields = ['actual_start_date', 'actual_end_date', 'actual_result']
        widgets = {name: forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}) for name in ['actual_start_date', 'actual_end_date']}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
        self.links = list(self.instance.indicator_links.select_related('indicator'))
        for link in self.links:
            if link.indicator.kind == ProjectIndicator.Kind.QUANTITATIVE:
                field = f'actual_{link.indicator_id}'
                self.fields[field] = forms.DecimalField(label=f'Факт: {link.indicator.title}', min_value=Decimal('0'), max_digits=15, decimal_places=3, help_text=f'План: {link.planned_value} {link.indicator.unit}')
                self.initial[field] = link.actual_value

    def clean(self):
        data = super().clean()
        if data.get('actual_start_date') and data.get('actual_end_date') and data['actual_end_date'] < data['actual_start_date']:
            self.add_error('actual_end_date', 'Дата окончания не может быть раньше даты начала.')
        if data.get('actual_end_date') and data['actual_end_date'] > timezone.localdate():
            self.add_error('actual_end_date', 'Проведённое мероприятие не может заканчиваться в будущем.')
        return data


class EventAttachmentForm(forms.Form):
    kind = forms.ChoiceField(label='Тип файла', choices=EventAttachment.Kind.choices, required=False, initial=EventAttachment.Kind.OTHER)
    file = forms.FileField(label='Файл', help_text='До 20 МБ. Фотографии и документы сохраняются для отчёта.')

    def clean_kind(self):
        return self.cleaned_data['kind'] or EventAttachment.Kind.OTHER

    def clean_file(self):
        file = self.cleaned_data['file']
        if file.size > 20 * 1024 * 1024:
            raise forms.ValidationError('Размер файла не должен превышать 20 МБ.')
        return file
