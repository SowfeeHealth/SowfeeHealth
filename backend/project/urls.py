# your_project/urls.py (the project-level urls.py)

from django.contrib import admin
from django.urls import path, include  # include() is necessary for routing app-specific URLs

urlpatterns = [
    path('admin/', admin.site.urls),  # Admin path
    path('', include('core.urls')),  # Include the core app's urls
,  # Add this line to match the empty root path
]
