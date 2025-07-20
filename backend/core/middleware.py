from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

class AdminAuthMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # Check if user is authenticated and is accessing admin
        if request.user.is_authenticated and request.user.is_superuser:
            # Set cookies only if they don't exist
            response.set_cookie(
                'is_superuser', 
                str(request.user.is_superuser).lower(), 
                max_age=3600*24*7, 
                path='/', 
                domain=settings.COOKIE_DOMAIN,
                secure=settings.COOKIE_SECURE,
                httponly=False,
                samesite='Lax'
            )
        else:
            response.set_cookie(
                'is_superuser', 
                'false', 
                path='/', 
                domain=settings.COOKIE_DOMAIN,
                secure=settings.COOKIE_SECURE,
                httponly=False,
                samesite='Lax'
            )
        return response