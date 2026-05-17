"""Seed default FlaggingRule for all existing institutions.

Idempotent: skips institutions that already have rules.
Safe to run multiple times (e.g. on every container start).

Usage:
    python manage.py seed_default_rules
"""

from django.core.management.base import BaseCommand
from django_tenants.utils import get_tenant_model, schema_context


class Command(BaseCommand):
    help = (
        "Seed default FlaggingRule for all existing institutions. "
        "Idempotent: skips institutions that already have rules. "
        "Safe to run multiple times (e.g. on every container start)."
    )

    DEFAULT_RULES = [
        # PHQ-9-style sum: loose cutoff for Sowfee 5-point scale
        # Note: Sowfee 1-5 Likert sums differ from PHQ-9 0-3 sums;
        # threshold 15 is approximate for 5-question depression set
        {
            'category': 'depression',
            'rule_type': 'sum',
            'threshold': 15,
            'comparison': 'gte',
            'severity': 'high',
            'description': 'High depression total (≥15)',
        },
        # Average rules: 3=Neutral, 4=Poor, 5=Very Poor (Sowfee Likert)
        {
            'category': 'stress',
            'rule_type': 'average',
            'threshold': 3,
            'comparison': 'gte',
            'severity': 'medium',
            'description': 'Elevated average stress (avg ≥3 = Neutral or worse)',
        },
        {
            'category': 'sleep',
            'rule_type': 'average',
            'threshold': 3,
            'comparison': 'gte',
            'severity': 'medium',
            'description': 'Sleep quality concern (avg ≥3 = Neutral or worse)',
        },
        # Any single question with severe score (wildcard across all categories)
        {
            'category': 'any',
            'rule_type': 'any_question',
            'threshold': 4,
            'comparison': 'gte',
            'severity': 'medium',
            'description': 'Any single question ≥4 (Poor or Very Poor)',
        },
    ]

    def handle(self, *args, **options):
        from surveys.models import FlaggingRule
        Tenant = get_tenant_model()

        total_seeded = 0
        total_skipped = 0

        for tenant in Tenant.objects.exclude(schema_name='public'):
            with schema_context(tenant.schema_name):
                if FlaggingRule.objects.exists():
                    self.stdout.write(
                        f"Skip {tenant.schema_name}: already has "
                        f"{FlaggingRule.objects.count()} rules"
                    )
                    total_skipped += 1
                    continue

                # FlaggingRule.objects.create() triggers save() override
                # → severity_order auto-synced from severity
                for rule_dict in self.DEFAULT_RULES:
                    FlaggingRule.objects.create(**rule_dict)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Seeded {tenant.schema_name}: "
                        f"{len(self.DEFAULT_RULES)} default rules"
                    )
                )
                total_seeded += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Seeded {total_seeded}, skipped {total_skipped}."
            )
        )
