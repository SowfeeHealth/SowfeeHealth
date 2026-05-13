"""
Management command to create a new tenant (institution) with its PostgreSQL schema.

Usage:
    python manage.py create_tenant --name="School A" --schema=school_a
    python manage.py create_tenant --name="School A" --schema=school_a --domain=schoola.localhost --regex=".*@schoola\.edu"
"""

from django.core.management.base import BaseCommand
from tenants.models import Institution, Domain


class Command(BaseCommand):
    help = 'Creates a new tenant (institution) with its own PostgreSQL schema'

    def add_arguments(self, parser):
        parser.add_argument('--name', required=True, help='Institution name')
        parser.add_argument('--schema', required=True, help='Schema name (lowercase, no spaces)')
        parser.add_argument('--domain', default='localhost', help='Domain for the tenant (default: localhost)')
        parser.add_argument('--regex', default=r'.*@.*\.edu', help='Email regex pattern for the institution')

    def handle(self, *args, **options):
        schema_name = options['schema']
        institution_name = options['name']
        domain_name = options['domain']
        regex_pattern = options['regex']

        if Institution.objects.filter(schema_name=schema_name).exists():
            self.stderr.write(self.style.ERROR(
                f'Tenant with schema "{schema_name}" already exists'
            ))
            return

        # auto_create_schema=True on the model triggers schema creation on save()
        tenant = Institution(
            schema_name=schema_name,
            institution_name=institution_name,
            institution_regex_pattern=regex_pattern,
        )
        tenant.save()

        Domain.objects.create(
            domain=domain_name,
            tenant=tenant,
            is_primary=True,
        )

        self.stdout.write(self.style.SUCCESS(
            f'Created tenant "{institution_name}" with schema "{schema_name}" '
            f'and domain "{domain_name}"'
        ))
