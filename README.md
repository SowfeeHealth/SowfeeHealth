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

### In progress: Crisis Detection Pipeline
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
│  Tier 1: Page MD     │  User UI: 988 popup  │
│  Tier 2: Queue MD    │  via WebSocket push  │
│  Tier 3: Log         │                      │
└──────────────────────┴──────────────────────┘