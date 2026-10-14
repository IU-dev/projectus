from django.contrib import admin
from .models import User, AuditEvent, BudgetTemplate, BudgetTemplateItem
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError


class TemplateItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            parent = form.cleaned_data.get('parent')
            if parent:
                parent_form = next((candidate for candidate in self.forms if candidate.instance.pk == parent.pk), None)
                if parent_form and (parent_form.cleaned_data.get('parent') or parent_form.cleaned_data.get('DELETE')):
                    raise ValidationError('Подстатья должна ссылаться на сохраняемую крупную статью без родителя.')


class TemplateItemInline(admin.TabularInline):
    model = BudgetTemplateItem
    formset = TemplateItemFormSet
    extra = 1
    fields = ['name', 'parent', 'explanation', 'position']

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        queryset = BudgetTemplateItem.objects.filter(template=obj, parent=None) if obj else BudgetTemplateItem.objects.none()
        class ScopedItemForm(formset.form):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.fields['parent'].queryset = queryset
        formset.form = ScopedItemForm
        return formset


@admin.register(BudgetTemplate)
class BudgetTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'active']
    inlines = [TemplateItemInline]

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "email_verified", "is_active", "is_superuser"]
    search_fields = ["email"]
    def has_module_permission(self, request):
        return request.user.is_superuser
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
