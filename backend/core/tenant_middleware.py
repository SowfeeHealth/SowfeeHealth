"""
Session-based tenant routing middleware for django-tenants.

Placed BEFORE AuthenticationMiddleware. Resolves the tenant from:
1. Hash link in the URL path (survey links) via SurveyHashLookup
2. Session key '_tenant_schema' (set during login)
3. Default: public schema (superusers, unauthenticated requests)
"""

import logging
import re
import uuid as uuid_mod

from django.core.cache import cache
from django.db import connection

from tenants.models import Institution, SurveyHashLookup

logger = logging.getLogger(__name__)

# Single combined pattern
HASH_LINK_PATTERN = re.compile(
    r'/api/(?:survey/link|get-user-survey-questions)/'
    r'(?P<hash_link>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/',
    re.IGNORECASE,
)

TENANT_CACHE_TTL = 300


class TenantSessionMiddleware:
    """
    Runs before AuthenticationMiddleware so the correct tenant schema is set
    before Django tries to load the User from the session.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        connection.set_schema_to_public()

        tenant = None

        # 0. Django admin always uses public schema
        from django.conf import settings
        if request.path.startswith(f'/{settings.ADMIN_URL}'):
            return self.get_response(request)

        # 1. Hash link URLs take priority (both registered and anonymous students)
        tenant = self._resolve_from_hash_link(request.path)

        # 2. Read tenant schema from session (set during login)
        if tenant is None and hasattr(request, 'session'):
            schema_name = request.session.get('_tenant_schema')
            if schema_name:
                tenant = self._get_tenant_by_schema(schema_name)

        # 3. Set tenant schema if resolved, otherwise stay on public
        if tenant is not None:
            connection.set_tenant(tenant)

        response = self.get_response(request)
        return response

    def _resolve_from_hash_link(self, path):
        """Resolve tenant from a hash_link UUID in the URL path."""
        match = HASH_LINK_PATTERN.search(path)
        if not match:
            return None

        raw = match.group('hash_link')

        try:
            uuid_mod.UUID(raw)
        except ValueError:
            return None

        # Check cache (hash_link -> schema_name string, JSON-safe)
        cache_key = f"hash_tenant:{raw}"
        cached_schema = cache.get(cache_key)
        if cached_schema is not None:
            return self._get_tenant_by_schema(cached_schema)

        try:
            lookup = SurveyHashLookup.objects.get(hash_link=raw)
            cache.set(cache_key, lookup.tenant.schema_name, timeout=TENANT_CACHE_TTL)
            return lookup.tenant
        except SurveyHashLookup.DoesNotExist:
            return None
        except Exception:
            logger.exception("Unexpected error resolving hash_link: %s", raw)
            return None

    def _get_tenant_by_schema(self, schema_name):
        """Load Institution by schema_name, with cache."""
        cache_key = f"tenant_schema:{schema_name}"
        tenant_id = cache.get(cache_key)
        if tenant_id is not None:
            try:
                return Institution.objects.get(pk=tenant_id)
            except Institution.DoesNotExist:
                cache.delete(cache_key)

        try:
            tenant = Institution.objects.get(schema_name=schema_name)
            cache.set(cache_key, tenant.pk, timeout=TENANT_CACHE_TTL)
            return tenant
        except Institution.DoesNotExist:
            return None
        except Exception:
            logger.exception("Unexpected error loading tenant: %s", schema_name)
            return None
