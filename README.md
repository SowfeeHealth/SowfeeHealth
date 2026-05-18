# Sowfee Health Survey Platform

A multi-tenant web application for educational institutions to create, distribute, and analyze student mental health surveys with schema-level data isolation.

🌐 **Live Demo:** [sowfeehealth.live](https://sowfeehealth.live)

## Overview

Sowfee Health enables institutions to run independent mental health survey programs on a shared platform. Each institution gets its own isolated PostgreSQL schema — students, surveys, responses, and chat data are physically separated at the database level. Admins manage survey templates, view analytics dashboards, and monitor flagged students within their institution's data boundary.

## Key Features

- **Multi-Tenant Architecture**: Schema-per-institution isolation using django-tenants — each institution's data lives in its own PostgreSQL schema
- **Custom Survey Builder**: Create and edit survey templates with Likert scale and text questions, custom answer choices, and category tagging (sleep, stress, support)
- **Analytics Dashboard**: Sleep quality distribution, stress level breakdown, flagged student tracking, monthly response rates — all scoped to the latest response per student
- **Secure Survey Distribution**: Each template generates a unique UUID hash link for anonymous or authenticated survey access
- **Session-Based Tenant Routing**: Custom middleware resolves tenant from session (login) or hash link (survey URLs) — no subdomain configuration required
- **Real-Time Chat**: WebSocket-based counselor-student messaging with per-tenant isolation
- **Role-Based Access Control**: Institution admin, counselor, and student roles with superuser lockout from all application views

## Tech Stack

**Backend:**
- Django + Django REST Framework
- PostgreSQL with django-tenants (schema-per-tenant)
- pgvector (PostgreSQL 16)
- Daphne (ASGI server for WebSocket support)
- Celery + Redis (async task processing and caching)

**AI / Moderation:**
- Anthropic Claude Sonnet 4.6 (Stage 2 clinical assessment, tool-use schema; sole content classifier)
- OpenAI GPT-4o-mini (Stage 2 failover, structured outputs via Pydantic)
- Microsoft Presidio + spaCy NER (Stage 0 PII redaction)
- Pydantic v2 (schema validation, LLM source-of-truth)

**Frontend:**
- React.js

**DevOps:**
- Docker Compose (development and production)
- GitHub Actions (CI/CD)
- AWS EC2 (production deployment)
- Nginx (reverse proxy + static files)
- Let's Encrypt (TLS)

## Multi-Tenant Architecture

```
┌─────────────────────────────────────────────────┐
│                 Public Schema                    │
│  tenants_institution    (tenant registry)        │
│  tenants_domain         (domain routing)         │
│  tenants_surveyhashlookup (hash → tenant map)    │
│  tenants_emailtenantmapping (email → schema)     │
│  accounts_user          (shared user table)       │
└─────────────────────────────────────────────────┘
┌──────────────────────┐  ┌──────────────────────┐
│  college_university   │  │  university_of_wash  │
│  ─────────────────── │  │  ─────────────────── │
│  accounts_user        │  │  accounts_user        │
│  surveys_*            │  │  surveys_*            │
│  chat_*               │  │  chat_*               │
│  (fully isolated)     │  │  (fully isolated)     │
└──────────────────────┘  └──────────────────────┘
```

- **Tenant creation**: Via Django admin — creates PostgreSQL schema and runs migrations automatically
- **Tenant routing**: `TenantSessionMiddleware` resolves tenant from session (`_tenant_schema`) or survey hash link UUID
- **Login flow**: `EmailTenantMapping` (public schema) maps user email to tenant schema before authentication
- **Data isolation**: Verified by 16 automated cross-tenant isolation tests

## Survey Moderation Pipeline

A 3-stage pipeline that runs on every survey submission. Stage 1a runs once at the survey level on Likert data; per-text-question stages run in parallel (`asyncio.gather`, Semaphore-bounded). Stage 2 Claude is the sole content classifier; the keyword filter is downgraded to audit + degraded-mode safety net.

```
┌─────────────────────────────────────────────────┐
│         SURVEY RESPONSE (text + Likert)         │
└──────────────────────┬──────────────────────────┘
                       │
        ┌──────────────┴──────────────────┐
        ▼ (Likert, survey-level 1x)        ▼ (text, N × parallel)
┌─────────────────┐         ┌──────────────────────┐
│ Stage 1a:       │         │ Stage 0: PII         │  Presidio + spaCy
│ Rule Engine     │         │ Redaction            │  fail-loud non-English
│ (Likert)        │         └──────────┬───────────┘
│ → rule severity │                    ▼
└────────┬────────┘         ┌──────────────────────┐
         │                  │ Stage 1c: Keyword    │  ~100 distress phrases
         │                  │ (audit + degraded-   │  audit-only normally;
         │                  │ mode safety net)     │  HIGH if Stage 2 fails
         │                  └──────────┬───────────┘
         │                              ▼
         │                  ┌──────────────────────┐
         │                  │ Stage 2: Clinical    │  Claude Sonnet 4.6
         │                  │ Assessment (ALWAYS   │  Anthropic primary,
         │                  │ runs in full mode)   │  GPT-4o-mini failover
         │                  │ → per-Q severity     │
         │                  └──────────┬───────────┘
         │                              │
         └──────────────────┬──────────┘
                            ▼
             ┌─────────────────────────────┐
             │ severity_max(rule_severity, │
             │   *per_question_severities) │
             └──────────────┬──────────────┘
                            ▼
           ┌────────────────────────────────┐
           │ CrisisAssessmentRecord per Q   │ → DB
           │ + SurveyResponse audit fields  │ → counselor dashboard
           └────────────────────────────────┘
```

**Stage details:**
- **Stage 0**: Microsoft Presidio + spaCy NER redact PII (PERSON, LOCATION, EMAIL, PHONE, etc.) before any external API call. Async via `asyncio.to_thread` to avoid blocking the event loop. Raises ValueError on non-English input rather than silently mis-tagging.
- **Stage 1a**: Likert rule engine aggregates per-category scores (depression, stress, sleep, support) against per-institution `FlaggingRule` thresholds. Rule types: `any_question` (wildcard), `sum`, `average`. Deterministic, no LLM cost. Runs once per survey at survey level.
- **Stage 1c**: Keyword filter (~100 phrases spanning suicide / self-harm / hopelessness / self-deprecation / academic distress / social isolation / emotional exhaustion). **Audit-only in normal operation** — matches are recorded on `CrisisAssessmentRecord.keyword_matches` for clinical review but do not gate Stage 2. **Degraded-mode safety net**: when Stage 2 both providers fail and a crisis keyword matched, severity escalates to HIGH so the signal is preserved.
- **Stage 2**: Claude Sonnet 4.6 via Anthropic tool use with structured assessment output (`severity`, `evidence_phrases`, `primary_concern`, `counselor_brief`, `confidence`). **Always runs in 'full' mode** for every text question — Stage 1b (Llama Guard) was removed after production testing revealed it misses implicit distress signals (academic failure, self-deprecation, social isolation) outside the MLCommons hazard taxonomy. GPT-4o-mini failover via OpenAI `beta.chat.completions.parse` with Pydantic `response_format`.

**Design highlights:**

- **Pydantic source-of-truth schema**: A single `AssessmentOutput` class generates both Anthropic tool `input_schema` (via `.model_json_schema()`) and OpenAI `response_format` (passed directly). Pattern inspired by the [Instructor library](https://python.useinstructor.com), used in production at OpenAI, Google, Microsoft, and AWS. Schema changes touch one Python class; both vendors stay in sync.

- **Semantic error taxonomy**: `BackendUnavailable` (transient infrastructure: timeout, rate limit, 5xx) vs `BackendInvalidOutput` (data/schema problem: hallucinated evidence, parse failure). The failover wrapper only catches the former; switching vendors won't fix a schema mismatch. Invalid output propagates to the pipeline, which marks `degraded_mode=True` on that question's assessment.

- **Evidence grounding**: LLM evidence phrases are validated against source text after the API call via case-insensitive substring match. Any hallucinated phrase triggers one retry with a stronger nudge; second failure raises `BackendInvalidOutput` rather than silently using ungrounded data. Counselors can trust that every quoted phrase traces to the student's actual words.

- **Failover transparency**: `AssessorWithFailover` implements the same `AssessmentBackend` protocol as a single backend. Pipeline code doesn't know failover exists — it just calls `assess()`. Provider attribution (`anthropic/claude-sonnet-4-6` vs `openai/gpt-4o-mini`) is recorded on each `CrisisAssessment` for audit and observability.

- **Atomic persistence**: Per-question `CrisisAssessmentRecord` rows and survey-level audit field updates (`final_severity`, `pipeline_latency_ms`, `inference_mode_used`, `flagged`) are wrapped in a single `transaction.atomic()` block in the Celery task — prevents partial-write inconsistency. The LLM API calls happen outside the atomic block (don't hold a DB transaction open for seconds).

- **Survey-level severity aggregation**: `severity_max(rule_severity, *per_question_severities)` — Stage 1a contributes survey-level rule severity independently of per-question Stage 2 verdicts, so a clinically-significant Likert score still flags the survey even if the LLM returns severity=NONE on all text questions.

## Code Structure

```
backend/
├── core/               # Settings, ASGI, tenant middleware
├── tenants/            # Institution, Domain, SurveyHashLookup, EmailTenantMapping
├── accounts/           # User model (SHARED_APPS + TENANT_APPS)
├── surveys/            # Templates, questions, responses, admin views, analytics
├── chat/               # WebSocket messaging, counselor-student assignments
├── tests/              # Cross-tenant isolation test suite
└── utils/              # Docker ops, env encryption
frontend_react/
└── src/
    ├── pages/          # Survey, Dashboard, Templates, Chat
    └── assets/         # CSS
```

## Deployment

Fully containerized with Docker Compose on AWS EC2:

- **web**: Django + Daphne (ASGI)
- **db**: pgvector/pgvector:pg16
- **redis**: Redis 7 Alpine (caching + Celery broker)
- **celery**: Async survey analysis worker
- **nginx**: Reverse proxy, static file serving, TLS termination

Startup runs `migrate_schemas` to apply migrations across all tenant schemas. CI/CD via GitHub Actions builds and pushes Docker images, then deploys to EC2.

## Features in Detail

### Survey Template Management
- Create, edit, and delete survey templates
- Add/edit/delete questions with Likert scale or text response types
- Category tagging: sleep quality, stress level, support perception, general
- Custom Likert answer labels per question
- Delete safeguard: warns when template has existing student responses

### Security & Authentication
- Role-based access: institution admin, counselor, student
- Superusers blocked from all application API views (403)
- Session-based tenant isolation — no cross-tenant data leakage
- CSRF protection on all endpoints

### Analytics Dashboard
- Sleep quality distribution (good/bad based on latest response per student)
- Stress level breakdown (low/moderate/high)
- Flagged student tracking (any Likert response >= 3)
- Monthly response rates and trends
- Support perception metrics

## Roadmap

- **v2 (current)**: Survey moderation pipeline — orchestration + DB integration + eval set
- **v3 (planned)**: Real-time chat moderation with async queue (SQS / Redis Stream) decoupling, keyword pre-filter + LLM analysis, and tier-based counselor routing

### Future improvement: Crisis Detection Pipeline (Chat)

```
┌─────────────────────────────────────────────┐
│           Chat Service (WebSocket)          │
│  - Real-time message delivery               │
│  - 1K concurrent connections                 │
└─────┬───────────────────────────────────────┘
      │
      │ Persist + publish
      ▼
┌─────────────────────────────────────────────┐
│         PostgreSQL (message storage)         │
│         + publish to SQS                     │
└─────┬───────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│           AWS SQS (or Redis Stream)          │
│  - Decouples chat from analysis              │
│  - Buffers traffic spikes                    │
│  - Enables retries                           │
└─────┬───────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│      Crisis Detection Worker(s)              │
│  Stage 1: Keyword filter (fast)              │
│  Stage 2: LLM analysis (only if Stage 1 hit) │
└─────┬───────────────────────────────────────┘
      │
      ▼
┌──────────────────────┬──────────────────────┐
│  Tier 1: Page counselor │ User UI: 988 popup  │
│  Tier 2: Queue counselor│ via WebSocket push  │
│  Tier 3: Log            │                     │
└─────────────────────────┴─────────────────────┘
```
