"""
Seeds the database with two test institutions and mock data.

Creates per institution:
  - 1 admin, 1 counselor, 3 students (tenant schema)
  - EmailTenantMapping entries (public schema)
  - 2 survey templates (1 active with 4 questions, 1 inactive)
  - SurveyHashLookup entries (public schema)
  - 3 registered + 1 anonymous survey responses
  - 1 counselor-student chat assignment with messages

Usage:
    python manage.py seed_tenants
    python manage.py seed_tenants --flush   # drop existing test tenants first
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context
from tenants.models import Institution, Domain, SurveyHashLookup, EmailTenantMapping
from accounts.models import User
from surveys.models import (
    SurveyTemplate, SurveyQuestion, SurveyResponse, QuestionResponse,
    AnonymousStudent, QuestionType, QuestionCategory,
)
from chat.models import CounselorStudentAssignment, Conversation, ChatMessage


TENANTS = [
    {
        'name': 'College University',
        'schema': 'college_university',
        'domain': 'cu',
        'regex': r'.+@cu\.edu',
        'suffix': '@cu.edu',
    },
    {
        'name': 'University of Washington',
        'schema': 'university_of_washington',
        'domain': 'uw',
        'regex': r'.+@uw\.edu',
        'suffix': '@uw.edu',
    },
]


class Command(BaseCommand):
    help = 'Seeds the database with two test institutions and mock data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Delete existing test tenants before seeding',
        )

    def handle(self, *args, **options):
        if options['flush']:
            self._flush()

        for cfg in TENANTS:
            self._create_tenant(cfg)

        self.stdout.write(self.style.SUCCESS('Seeding complete.'))

    def _flush(self):
        schemas = [c['schema'] for c in TENANTS]
        for cfg in TENANTS:
            try:
                tenant = Institution.objects.get(schema_name=cfg['schema'])
                tenant.delete(force_drop=True)
                self.stdout.write(f'  Dropped tenant "{cfg["name"]}"')
            except Institution.DoesNotExist:
                pass
        EmailTenantMapping.objects.filter(schema_name__in=schemas).delete()

    def _create_tenant(self, cfg):
        if Institution.objects.filter(schema_name=cfg['schema']).exists():
            self.stderr.write(self.style.WARNING(
                f'Tenant "{cfg["name"]}" already exists — skipping. '
                f'Use --flush to recreate.'
            ))
            return

        tenant = Institution(
            schema_name=cfg['schema'],
            institution_name=cfg['name'],
            institution_regex_pattern=cfg['regex'],
        )
        tenant.save()
        Domain.objects.create(domain=cfg['domain'], tenant=tenant, is_primary=True)
        self.stdout.write(f'  Created tenant "{cfg["name"]}" (schema: {cfg["schema"]})')

        connection.set_tenant(tenant)
        try:
            self._seed_users(tenant, cfg)
            self._seed_surveys(tenant, cfg)
            self._seed_chat(cfg)
        finally:
            connection.set_schema_to_public()

    def _seed_users(self, tenant, cfg):
        s = cfg['suffix']

        admin = User.objects.create_admin(
            email=f'admin{s}', password='testpass123',
            institution_details=tenant,
        )

        counselor = User.objects.create_user(
            email=f'counselor{s}', password='testpass123',
        )
        counselor.role = User.Role.COUNSELOR
        counselor.name = f'{cfg["name"]} Counselor'
        counselor.institution_details = tenant
        counselor.save()

        students = []
        for i in range(1, 4):
            students.append(User.objects.create_student(
                email=f'student{i}{s}', password='testpass123',
                institution_details=tenant,
                name=f'{cfg["name"]} Student {i}',
            ))

        with schema_context('public'):
            for u in [admin, counselor] + students:
                EmailTenantMapping.objects.get_or_create(
                    email=u.email,
                    defaults={'schema_name': cfg['schema']},
                )

        self.stdout.write(f'    Users: 1 admin, 1 counselor, 3 students')

    def _seed_surveys(self, tenant, cfg):
        t1 = SurveyTemplate.objects.create(used=True)
        with schema_context('public'):
            SurveyHashLookup.objects.create(hash_link=t1.hash_link, tenant=tenant)

        questions = []
        for text, qtype, cat, order in [
            ('How would you rate your sleep quality?',
             QuestionType.LIKERT, QuestionCategory.SLEEP, 1),
            ('How stressed do you feel this week?',
             QuestionType.LIKERT, QuestionCategory.STRESS, 2),
            ('Do you feel supported by your peers?',
             QuestionType.LIKERT, QuestionCategory.SUPPORT, 3),
            ('Describe how you have been feeling lately.',
             QuestionType.TEXT, QuestionCategory.GENERAL, 4),
        ]:
            questions.append(SurveyQuestion.objects.create(
                survey_template=t1, question_text=text,
                question_type=qtype, category=cat, order=order,
            ))

        t2 = SurveyTemplate.objects.create(used=False)
        with schema_context('public'):
            SurveyHashLookup.objects.create(hash_link=t2.hash_link, tenant=tenant)

        students = list(User.objects.filter(role=User.Role.STUDENT).order_by('email'))
        likert_sets = [
            [2, 1, 2],  # good sleep, low stress, supported
            [4, 4, 4],  # bad sleep, high stress, unsupported — flagged
            [3, 3, 3],  # moderate
        ]
        for student, vals in zip(students, likert_sets):
            sr = SurveyResponse.objects.create(
                student=student, survey_template=t1,
                flagged=(max(vals) >= 3),
            )
            for q, v in zip(questions[:3], vals):
                QuestionResponse.objects.create(
                    survey_response=sr, question=q, likert_value=v,
                )
            QuestionResponse.objects.create(
                survey_response=sr, question=questions[3],
                text_response='Feeling okay overall.',
            )

        s = cfg['suffix']
        anon = AnonymousStudent.objects.create(
            email=f'anon{s}', name='Anonymous User', survey_template=t1,
        )
        sr_anon = SurveyResponse.objects.create(
            anonymous_student=anon, survey_template=t1, flagged=True,
        )
        for q, v in zip(questions[:3], [5, 5, 5]):
            QuestionResponse.objects.create(
                survey_response=sr_anon, question=q, likert_value=v,
            )
        QuestionResponse.objects.create(
            survey_response=sr_anon, question=questions[3],
            text_response='Not doing well at all.',
        )

        self.stdout.write(
            f'    Surveys: 2 templates, 4 questions, '
            f'4 responses (1 anonymous, 1 flagged registered)'
        )

    def _seed_chat(self, cfg):
        s = cfg['suffix']
        counselor = User.objects.get(email=f'counselor{s}')
        student = User.objects.get(email=f'student1{s}')

        assignment = CounselorStudentAssignment.objects.create(
            counselor=counselor, student=student, is_active=True,
        )
        # Conversation is auto-created by post_save signal in chat.signals
        convo = assignment.conversations

        for seq, (sender, text) in enumerate([
            (student, 'Hi, I have been struggling with sleep lately.'),
            (counselor, 'I am sorry to hear that. Can you tell me more?'),
            (student, 'I usually stay up until 3am and wake up at 7am.'),
            (counselor, 'Let us work on a sleep schedule together.'),
        ], start=1):
            ChatMessage.objects.create(
                conversation=convo, sender=sender,
                content=text, server_seq=seq,
            )

        self.stdout.write(f'    Chat: 1 assignment, 4 messages')
