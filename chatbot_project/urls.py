# project/urls.py

from django.contrib import admin
from django.urls import path, include

# Import settings and serve
from django.conf import settings
from django.views.static import serve # <-- Import serve

# Remove the line below if you had it:
# from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('api/users/', include('users.urls')),
    path('', include('chat.urls')),
]

# Add this block *only in development* to explicitly serve static files
# from the chat app's static directory.
if settings.DEBUG:
    urlpatterns += [
        # This pattern captures anything after /static/ and passes it as 'path'
        # to the serve view. The serve view looks for the file by joining
        # the document_root with the captured path.
        path('static/<path:path>', serve, {'document_root': settings.BASE_DIR / 'chat' / 'static'}),
    ]