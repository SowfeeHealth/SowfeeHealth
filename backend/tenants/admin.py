from django.contrib import admin
from .models import Institution, Domain, SurveyHashLookup, EmailTenantMapping


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 1


class InstitutionAdmin(admin.ModelAdmin):
    list_display = ('institution_name', 'schema_name', 'institution_regex_pattern')
    search_fields = ('institution_name',)
    inlines = [DomainInline]


admin.site.register(Institution, InstitutionAdmin)
admin.site.register(Domain)
admin.site.register(SurveyHashLookup)
admin.site.register(EmailTenantMapping)
