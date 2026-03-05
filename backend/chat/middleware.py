from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from importlib import import_module
from django.conf import settings

User = get_user_model()


class SessionAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        scope['user'] = await self.get_user(scope)
        return await super().__call__(scope, receive, send)

    @database_sync_to_async
    def get_user(self, scope):
        cookies = {}
        for header in scope.get('headers', []):
            if header[0] == b'cookie':
                for item in header[1].decode().split(';'):
                    item = item.strip()
                    if '=' in item:
                        k, v = item.split('=', 1)
                        cookies[k.strip()] = v.strip()

        session_key = cookies.get('auth_token')
        print(f"[WS DEBUG] all cookies: {cookies}")
        print(f"[WS DEBUG] auth_token: {session_key}")

        if not session_key:
            return AnonymousUser()

        try:
            engine = import_module(settings.SESSION_ENGINE)
            session = engine.SessionStore(session_key=session_key)
            print(f"[WS DEBUG] SESSION_ENGINE: {settings.SESSION_ENGINE}")
            print(f"[WS DEBUG] session exists: {session.exists(session_key)}")
            print(f"[WS DEBUG] session data: {dict(session)}")

            user_id = session.get('_auth_user_id')
            print(f"[WS DEBUG] user_id: {user_id}")

            if not user_id:
                return AnonymousUser()
            return User.objects.get(pk=user_id)
        except Exception as e:
            print(f"[WS DEBUG] exception: {e}")
            return AnonymousUser()