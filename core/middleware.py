from django.conf import settings
from django.shortcuts import render
from django.contrib.auth import logout


# core/middleware.py

from django.shortcuts import render
from django.contrib.auth import logout
from django.core.cache import cache
from .models import SiteSettings
import threading

_local = threading.local()


def get_current_user():
    return getattr(_local, 'user', None)

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.user = getattr(request, 'user', None)
        return self.get_response(request)


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # 🔥 читаем из кеша, чтобы не бить БД каждый раз
        maintenance = cache.get('maintenance_mode')

        if maintenance is None:
            try:
                settings_obj = SiteSettings.objects.first()
                maintenance = settings_obj.maintenance if settings_obj else False
            except Exception:
                maintenance = False

            cache.set('maintenance_mode', maintenance, 10)  # 10 сек

        if not maintenance:
            return self.get_response(request)

        # --- разрешённые пути ---
        if (
            request.path.startswith('/admin/')
            or request.path.startswith('/static/')
            or request.path.startswith('/media/')
        ):
            return self.get_response(request)

        if get_client_ip(request) in settings.DEV_IPS:
            return self.get_response(request)

        # --- доступ для разработчиков ---
        if request.user.is_authenticated:
            if request.user.is_superuser or request.user.has_perm('core.bypass_maintenance'):
                return self.get_response(request)

            # ❌ остальные — логаут
            logout(request)

        return render(request, 'maintenance.html', status=503)

