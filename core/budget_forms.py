from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import BudgetSection, BudgetLine, BudgetTemplate, PaymentOrder, FundReceipt
from .budget_services import active_revision, approver_candidates, eligible_approver_ids, validate_recipient, validate_approvers


class SectionForm(forms.ModelForm):
    parent = forms.ChoiceField(label="Крупная статья", required=False)

    class Meta:
        model = BudgetSection
        fields = ["name", "explanation", "position"]

    def __init__(self, *args, revision, **kwargs):
        super().__init__(*args, **kwargs)
        self.parents = {str(section.pk): section for section in revision.sections.filter(parent=None).exclude(pk=self.instance.pk)}
        self.fields["parent"].choices = [("", "— Крупная статья —"), *[(pk, section.name) for pk, section in self.parents.items()]]
        self.initial["parent"] = str(self.instance.parent_id) if self.instance.parent_id else ""

    def clean(self):
        data = super().clean()
        self.instance.parent = self.parents.get(data.get("parent"))
        return data


class LineForm(forms.ModelForm):
    section = forms.ChoiceField(label="Статья / подстатья")

    class Meta:
        model = BudgetLine
        fields = ["name", "unit_price", "quantity", "unit_name", "total_amount", "cofinancing_amount", "requested_amount", "comment", "position"]

    def __init__(self, *args, revision, **kwargs):
        super().__init__(*args, **kwargs)
        sections = list(revision.sections.select_related("parent"))
        parents = {section.parent_id for section in sections if section.parent_id}
        self.sections = {str(section.pk): section for section in sections if section.pk not in parents}
        self.fields["section"].choices = [(pk, f"{section.parent.name} / {section.name}" if section.parent_id else section.name) for pk, section in self.sections.items()]
        if self.instance.section_id:
            self.initial["section"] = str(self.instance.section_id)
        self.fields["total_amount"].help_text = "Общая стоимость = софинансирование + запрашиваемая сумма. Если указаны цена и количество — также их произведение."

    def clean(self):
        data = super().clean()
        section = self.sections.get(data.get("section"))
        if section:
            self.instance.section = section
        return data


class TemplateForm(forms.Form):
    template = forms.ChoiceField(label="Шаблон статей")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].choices = [(str(template.pk), template.name) for template in BudgetTemplate.objects.filter(active=True)]


class RevisionForm(forms.Form):
    kind = forms.ChoiceField(label="Вид изменения", choices=[("amendment", "Изменение сметы"), ("transfer", "Перенос средств")])
    reason = forms.CharField(label="Причина", widget=forms.Textarea)


class DecisionForm(forms.Form):
    comment = forms.CharField(label="Комментарий", widget=forms.Textarea, required=False)


class SettingsForm(forms.Form):
    approvers = forms.MultipleChoiceField(label="Каждый из выбранных людей должен согласовать платёж", required=False, widget=forms.CheckboxSelectMultiple)
    require_payment_bank_details = forms.BooleanField(label="Требовать банковские реквизиты для проведения платежа", required=False,
        help_text="Включено: счёт, банк, БИК и корреспондентский счёт обязательны. Выключено: допускается устное согласование или учёт уже проведённых оплат; банковские поля необязательны. Получатель и ИНН обязательны всегда.")

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.candidates = {str(pk): user for pk, user in approver_candidates(project).items()}
        eligible = eligible_approver_ids(project)
        self.fields["approvers"].choices = [(pk, (user.get_full_name() or user.email) + (" — нет права согласования платежей" if user.pk not in eligible else "")) for pk, user in self.candidates.items()]
        self.initial["approvers"] = [str(entry.user_id) for entry in project.payment_approvers.all()]
        self.initial["require_payment_bank_details"] = project.require_payment_bank_details

    def clean_approvers(self):
        users = [self.candidates[pk] for pk in self.cleaned_data["approvers"]]
        validate_approvers(self.project, users)
        return users


class ReceiptForm(forms.ModelForm):
    class Meta:
        model = FundReceipt
        fields = ["amount", "received_date", "comment"]
        widgets = {"received_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["comment"].help_text = "Поступление нельзя изменить или удалить после сохранения. Проверьте сумму и дату."


class PaymentForm(forms.ModelForm):
    budget_line = forms.ChoiceField(label="Строка действующей сметы")
    events = forms.MultipleChoiceField(label="Связанные мероприятия", required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = PaymentOrder
        fields = ["amount", "description", "recipient_type", "recipient_name", "inn", "kpp", "account", "bank_name", "bik", "correspondent_account"]

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        revision = active_revision(project)
        self.lines = {str(line.key): line for line in revision.lines.select_related("section__parent")} if revision else {}
        self.fields["budget_line"].choices = [(key, f"{line.section.name} / {line.name}") for key, line in self.lines.items()]
        self.fields["events"].choices = [(str(event.pk), event.title) for event in project.project_events.all()]
        if self.instance.pk:
            self.initial["budget_line"] = str(self.instance.budget_line_key)
            self.initial["events"] = [str(event.pk) for event in self.instance.events.all()]
        self.fields["inn"].help_text = "12 цифр для физического лица / ИП; 10 для организации. КПП — только для организации (9 цифр)."
        self.fields["account"].help_text = "Банковские реквизиты обязательны при отправке." if project.require_payment_bank_details else "Банковские реквизиты необязательны в этом проекте."

    def clean(self):
        data = super().clean()
        if any(self.data.get(field) for field in ["payment_document_date", "payment_document_number", "payment_purpose", "executed_by", "executed_at"]):
            raise ValidationError("Дату, номер документа и назначение платежа заполняет только исполнитель при исполнении.")
        candidate = PaymentOrder(**{field: data.get(field, "") for field in ["recipient_type", "recipient_name", "inn", "kpp", "account", "bank_name", "bik", "correspondent_account"]})
        try:
            validate_recipient(candidate, False)
        except ValidationError as exc:
            for field, errors in exc.message_dict.items():
                if field not in self.errors:
                    self.add_error(field, errors)
        for field in ["inn", "kpp", "account", "bik", "correspondent_account"]:
            if field in data:
                data[field] = getattr(candidate, field)
        return data


class ExecutionForm(forms.Form):
    payment_document_date = forms.DateField(label="Дата платежного документа", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    payment_document_number = forms.CharField(label="Номер платежного документа", max_length=100)
    payment_purpose = forms.CharField(label="Назначение платежа", widget=forms.Textarea)

    def clean_payment_document_date(self):
        date = self.cleaned_data["payment_document_date"]
        if date > timezone.localdate():
            raise ValidationError("Дата платежного документа не может быть в будущем.")
        return date


class AttachmentForm(forms.Form):
    file = forms.FileField(label="Подтверждающий файл", help_text="До 20 МБ. Можно последовательно добавить несколько файлов.")

    def clean_file(self):
        file = self.cleaned_data["file"]
        if file.size > 20 * 1024 * 1024:
            raise ValidationError("Размер файла не должен превышать 20 МБ.")
        return file
