import logging

from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.db import connection
from django_tenants.utils import schema_context
from importlib import import_module
from django.conf import settings

from tenants.models import Institution

User = get_user_model()
logger = logging.getLogger(__name__)


class SessionAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        user, session = await self.get_user_and_session(scope)
        scope['user'] = user
        scope['session'] = session
        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def get_user_and_session(self, scope):
        cookies = {}
        for header in scope.get('headers', []):
            if header[0] == b'cookie':
                for item in header[1].decode().split(';'):
                    item = item.strip()
                    if '=' in item:
                        k, v = item.split('=', 1)
                        cookies[k.strip()] = v.strip()

        session_key = cookies.get('auth_token')
        if not session_key:
            return AnonymousUser(), {}

        try:
            engine = import_module(settings.SESSION_ENGINE)
            session = engine.SessionStore(session_key=session_key)

            user_id = session.get('_auth_user_id')
            if not user_id:
                return AnonymousUser(), dict(session)

            # Set tenant schema before loading User (User is per-tenant)
            schema_name = session.get('_tenant_schema')
            if schema_name:
                try:
                    tenant = Institution.objects.get(schema_name=schema_name)
                    connection.set_tenant(tenant)
                except Institution.DoesNotExist:
                    pass

            user = User.objects.get(pk=user_id)
            return user, dict(session)
        except Exception as e:
            logger.exception("WebSocket auth error")
            return AnonymousUser(), {}