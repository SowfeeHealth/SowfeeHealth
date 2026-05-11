"""
Cross-tenant isolation tests for django-tenants schema separation.

Verifies:
  - Data in tenant A is invisible from tenant B (users, surveys, chat)
  - SurveyHashLookup routes hash links to the correct tenant
  - Superusers are blocked (403) from all application API views

Requires a PostgreSQL backend (django-tenants creates real schemas).
Uses TransactionTestCase because schema creation needs COMMIT.
"""

import uuid

from django.db import connection
from django.test import TransactionTestCase
from django_tenants.utils import schema_context
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from chat.models import (
    ChatMessage, CounselorStudentAssignment,
)
from chat.views import assignments
from surveys.admin_views import (
    dashboard_api, flagged_responses_view, flagged_students_view,
    student_response_view, students_view,
)
from surveys.models import (
    AnonymousStudent, QuestionCategory, QuestionResponse, QuestionType,
    SurveyQuestion, SurveyResponse, SurveyTemplate,
)
from tenants.models import Domain, Institution, SurveyHashLookup


class TenantIsolationTest(TransactionTestCase):
    """
    Creates two tenants with independent data and asserts zero cross-tenant
    leakage at the ORM level, plus superuser 403 blocking at the view level.
    """

    def _fixture_teardown(self):
        # django-tenants cross-schema FKs prevent TRUNCATE without CASCADE.
        # Our tearDown drops schemas explicitly, so skip the default flush.
        pass

    def setUp(self):
        connection.set_schema_to_public()

        # ── Tenant A ──────────────────────────────────────────────────
        self.tenant_a = Institution(
            schema_name='test_a',
            institution_name='Test School A',
            institution_regex_pattern=r'.*@testa\.edu',
        )
        self.tenant_a.save()
        Domain.objects.create(
            domain='testa.localhost', tenant=self.tenant_a, is_primary=True,
        )

        with schema_context('test_a'):
            self.admin_a = User.objects.create_admin(
                email='admin@testa.edu', password='pass',
                institution_details=self.tenant_a,
            )
            self.student_a = User.objects.create_student(
                email='student@testa.edu', password='pass',
                institution_details=self.tenant_a, name='Student A',
            )
            counselor_a = User.objects.create_user(
                email='counselor@testa.edu', password='pass',
            )
            counselor_a.role = User.Role.COUNSELOR
            counselor_a.institution_details = self.tenant_a
            counselor_a.save()

            self.template_a = SurveyTemplate.objects.create(
                used=True,
            )
            self.q_a = SurveyQuestion.objects.create(
                survey_template=self.template_a,
                question_text='Sleep quality?',
                question_type=QuestionType.LIKERT,
                category=QuestionCategory.SLEEP, order=1,
            )
            self.response_a = SurveyResponse.objects.create(
                student=self.student_a, survey_template=self.template_a,
            )
            QuestionResponse.objects.create(
                survey_response=self.response_a, question=self.q_a,
                likert_value=3,
            )

            self.anon_a = AnonymousStudent.objects.create(
                email='anon@testa.edu', name='Anon A',
                survey_template=self.template_a,
            )
            sr_anon_a = SurveyResponse.objects.create(
                anonymous_student=self.anon_a,
                survey_template=self.template_a, flagged=True,
            )
            QuestionResponse.objects.create(
                survey_response=sr_anon_a, question=self.q_a,
                likert_value=5,
            )

            self.assignment_a = CounselorStudentAssignment.objects.create(
                counselor=counselor_a, student=self.student_a, is_active=True,
            )
            # Conversation auto-created by post_save signal in chat.signals
            convo_a = self.assignment_a.conversations
            ChatMessage.objects.create(
                conversation=convo_a, sender=self.student_a,
                content='Hello from A', server_seq=1,
            )

        SurveyHashLookup.objects.create(
            hash_link=self.template_a.hash_link, tenant=self.tenant_a,
        )

        # ── Tenant B ──────────────────────────────────────────────────
        self.tenant_b = Institution(
            schema_name='test_b',
            institution_name='Test School B',
            institution_regex_pattern=r'.*@testb\.edu',
        )
        self.tenant_b.save()
        Domain.objects.create(
            domain='testb.localhost', tenant=self.tenant_b, is_primary=True,
        )

        with schema_context('test_b'):
            self.admin_b = User.objects.create_admin(
                email='admin@testb.edu', password='pass',
                institution_details=self.tenant_b,
            )
            self.student_b = User.objects.create_student(
                email='student@testb.edu', password='pass',
                institution_details=self.tenant_b, name='Student B',
            )
            counselor_b = User.objects.create_user(
                email='counselor@testb.edu', password='pass',
            )
            counselor_b.role = User.Role.COUNSELOR
            counselor_b.institution_details = self.tenant_b
            counselor_b.save()

            self.template_b = SurveyTemplate.objects.create(
                used=True,
            )
            self.q_b = SurveyQuestion.objects.create(
                survey_template=self.template_b,
                question_text='Stress level?',
                question_type=QuestionType.LIKERT,
                category=QuestionCategory.STRESS, order=1,
            )
            self.response_b = SurveyResponse.objects.create(
                student=self.student_b, survey_template=self.template_b,
                flagged=True,
            )
            QuestionResponse.objects.create(
                survey_response=self.response_b, question=self.q_b,
                likert_value=5,
            )

            self.assignment_b = CounselorStudentAssignment.objects.create(
                counselor=counselor_b, student=self.student_b, is_active=True,
            )
            convo_b = self.assignment_b.conversations
            ChatMessage.objects.create(
                conversation=convo_b, sender=self.student_b,
                content='Hello from B', server_seq=1,
            )

        SurveyHashLookup.objects.create(
            hash_link=self.template_b.hash_link, tenant=self.tenant_b,
        )

        connection.set_schema_to_public()

    def tearDown(self):
        connection.set_schema_to_public()
        for tenant in [self.tenant_a, self.tenant_b]:
            try:
                tenant.delete(force_drop=True)
            except Exception:
                pass
        super().tearDown()

    # ── Schema-level data isolation ───────────────────────────────────

    def test_users_isolated_between_schemas(self):
        with schema_context('test_a'):
            emails_a = set(User.objects.values_list('email', flat=True))
        with schema_context('test_b'):
            emails_b = set(User.objects.values_list('email', flat=True))

        self.assertIn('student@testa.edu', emails_a)
        self.assertNotIn('student@testb.edu', emails_a)
        self.assertIn('student@testb.edu', emails_b)
        self.assertNotIn('student@testa.edu', emails_b)

    def test_survey_responses_isolated(self):
        with schema_context('test_a'):
            count_a = SurveyResponse.objects.count()
            registered_email_a = SurveyResponse.objects.filter(
                student__isnull=False,
            ).first().student.email
            anon_email_a = SurveyResponse.objects.filter(
                anonymous_student__isnull=False,
            ).first().anonymous_student.email
        with schema_context('test_b'):
            count_b = SurveyResponse.objects.count()
            registered_email_b = SurveyResponse.objects.filter(
                student__isnull=False,
            ).first().student.email
            anon_count_b = SurveyResponse.objects.filter(
                anonymous_student__isnull=False,
            ).count()

        self.assertEqual(count_a, 2)  # 1 registered + 1 anonymous
        self.assertEqual(count_b, 1)  # 1 registered only
        self.assertEqual(registered_email_a, 'student@testa.edu')
        self.assertEqual(anon_email_a, 'anon@testa.edu')
        self.assertEqual(registered_email_b, 'student@testb.edu')
        self.assertEqual(anon_count_b, 0)

    def test_survey_templates_isolated(self):
        with schema_context('test_a'):
            hash_a = SurveyTemplate.objects.first().hash_link
        with schema_context('test_b'):
            hash_b = SurveyTemplate.objects.first().hash_link

        self.assertNotEqual(hash_a, hash_b)

    def test_question_responses_isolated(self):
        with schema_context('test_a'):
            vals_a = set(
                QuestionResponse.objects.values_list('likert_value', flat=True),
            )
        with schema_context('test_b'):
            vals_b = set(
                QuestionResponse.objects.values_list('likert_value', flat=True),
            )

        self.assertEqual(vals_a, {3, 5})  # registered=3, anonymous=5
        self.assertEqual(vals_b, {5})

    def test_anonymous_students_isolated(self):
        with schema_context('test_a'):
            anon_a = AnonymousStudent.objects.count()
        with schema_context('test_b'):
            anon_b = AnonymousStudent.objects.count()

        self.assertEqual(anon_a, 1)
        self.assertEqual(anon_b, 0)

    def test_chat_messages_isolated(self):
        with schema_context('test_a'):
            msgs_a = list(
                ChatMessage.objects.values_list('content', flat=True),
            )
        with schema_context('test_b'):
            msgs_b = list(
                ChatMessage.objects.values_list('content', flat=True),
            )

        self.assertEqual(msgs_a, ['Hello from A'])
        self.assertEqual(msgs_b, ['Hello from B'])

    def test_assignments_isolated(self):
        with schema_context('test_a'):
            count_a = CounselorStudentAssignment.objects.count()
        with schema_context('test_b'):
            count_b = CounselorStudentAssignment.objects.count()

        self.assertEqual(count_a, 1)
        self.assertEqual(count_b, 1)

    def test_cross_schema_query_returns_zero(self):
        """Querying tenant A data with tenant B's schema yields nothing."""
        with schema_context('test_b'):
            leaked = User.objects.filter(email='student@testa.edu').exists()
        self.assertFalse(leaked)

    # ── Hash link routing ─────────────────────────────────────────────

    def test_hash_link_resolves_to_correct_tenant(self):
        lookup_a = SurveyHashLookup.objects.get(
            hash_link=self.template_a.hash_link,
        )
        lookup_b = SurveyHashLookup.objects.get(
            hash_link=self.template_b.hash_link,
        )

        self.assertEqual(lookup_a.tenant, self.tenant_a)
        self.assertEqual(lookup_b.tenant, self.tenant_b)

    def test_unknown_hash_link_returns_no_result(self):
        self.assertFalse(
            SurveyHashLookup.objects.filter(hash_link=uuid.uuid4()).exists(),
        )

    # ── Superuser 403 blocking ────────────────────────────────────────

    def _superuser_get(self, view_fn):
        """Fire a GET at the view as a superuser, return the response."""
        factory = APIRequestFactory()
        superuser = User(email='super@admin.com', is_superuser=True)
        request = factory.get('/fake/')
        force_authenticate(request, user=superuser)
        return view_fn(request)

    def test_superuser_blocked_from_dashboard(self):
        self.assertEqual(self._superuser_get(dashboard_api).status_code, 403)

    def test_superuser_blocked_from_student_responses(self):
        self.assertEqual(
            self._superuser_get(student_response_view).status_code, 403,
        )

    def test_superuser_blocked_from_flagged_responses(self):
        self.assertEqual(
            self._superuser_get(flagged_responses_view).status_code, 403,
        )

    def test_superuser_blocked_from_students(self):
        self.assertEqual(self._superuser_get(students_view).status_code, 403)

    def test_superuser_blocked_from_flagged_students(self):
        self.assertEqual(
            self._superuser_get(flagged_students_view).status_code, 403,
        )

    def test_superuser_blocked_from_assignments(self):
        self.assertEqual(
            self._superuser_get(assignments).status_code, 403,
        )
