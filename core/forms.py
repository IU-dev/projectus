from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User, ProjectRequest, Project, ProjectIndicator
from .permissions import ProjectPermission, SystemPermission
class RegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["email", "first_name", "last_name"]
    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Этот email уже зарегистрирован.")
        return email
class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email")
    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.email_verified:
            raise forms.ValidationError("Подтвердите email перед входом.", code="unverified")
class RequestForm(forms.ModelForm):
    class Meta:
        model = ProjectRequest
        fields = ["title", "description"]
class ProjectListWidget(forms.Textarea):
    def value_from_datadict(self, data, files, name):
        return data.getlist(name) if hasattr(data, "getlist") else data.get(name, [])

    def format_value(self, value):
        return "\n".join(value) if isinstance(value, list) else value


class ProjectListField(forms.CharField):
    widget = ProjectListWidget

    def prepare_value(self, value):
        return value if isinstance(value, list) else [value or ""]

    def to_python(self, value):
        items = value if isinstance(value, list) else [value or ""]
        return [line.strip() for item in items for line in item.splitlines() if line.strip()]


class ProjectForm(forms.ModelForm):
    goals = ProjectListField(label="Цели проекта", required=False)
    tasks = ProjectListField(label="Задачи проекта", required=False)

    class Meta:
        model = Project
        fields = ["title", "description", "goals", "tasks", "start_date", "end_date"]
        labels = {"description": "Краткое описание проекта"}
        widgets = {
            "start_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "end_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def clean(self):
        data = super().clean()
        if data.get("start_date") and data.get("end_date") and data["end_date"] < data["start_date"]:
            self.add_error("end_date", "Конечная дата не может быть раньше начальной.")
        return data
class IndicatorForm(forms.ModelForm):
    class Meta:
        model = ProjectIndicator
        fields = ["kind", "title", "target_value", "unit", "result", "achieved"]
        widgets = {"title": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["kind"].disabled = True
        else:
            self.initial["kind"] = ProjectIndicator.Kind.QUALITATIVE

    def clean(self):
        data = super().clean()
        if data.get("kind") == ProjectIndicator.Kind.QUANTITATIVE:
            if data.get("target_value") is None and "target_value" not in self.errors:
                self.add_error("target_value", "Укажите целевое значение больше нуля.")
            data["result"] = ""
            data["achieved"] = False
        elif data.get("kind") == ProjectIndicator.Kind.QUALITATIVE:
            data["target_value"] = None
            data["unit"] = ""
        return data


class PermissionForm(forms.Form):
    permissions = forms.MultipleChoiceField(label="Разрешенные действия", choices=ProjectPermission.choices, widget=forms.CheckboxSelectMultiple, required=False)
class InvitationForm(PermissionForm):
    email = forms.EmailField(label="Email участника", help_text="Можно пригласить только пользователя, уже зарегистрированного в Projectus.")
    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Пользователь не зарегистрирован. Сначала нужна регистрация в Projectus.")
        return email
class SystemGrantForm(forms.Form):
    user_id = forms.IntegerField(label="Пользователь", min_value=1, max_value=9223372036854775807, widget=forms.HiddenInput)
    permissions = forms.MultipleChoiceField(label="Полномочия", choices=SystemPermission.choices, widget=forms.CheckboxSelectMultiple, required=False)
class DecisionForm(forms.Form):
    decision = forms.ChoiceField(label="Решение", choices=[("approve", "Одобрить"), ("reject", "Отклонить")])
    note = forms.CharField(label="Комментарий", widget=forms.Textarea, required=False)
    def clean(self):
        data = super().clean()
        if data.get("decision") == "reject" and not data.get("note", "").strip():
            self.add_error("note", "Укажите причину отклонения.")
        return data
class EmailForm(forms.Form):
    email = forms.EmailField(label="Email")
