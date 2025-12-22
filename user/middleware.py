from django.utils import timezone

class UpdateLastSeenMiddleware:
    """
    Обновляет last_seen для каждого запроса авторизованного пользователя
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            profile = getattr(request.user, 'profile', None)
            if profile:
                profile.last_seen = timezone.now()
                profile.save(update_fields=['last_seen'])
        return response
    
from django.shortcuts import redirect
from django.urls import reverse

class RequireServernameMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        # страницы, которые ВСЕГДА доступны
        allowed_paths = [
            reverse('complete_profile'),
            reverse('logout'),
        ]

        if request.path.startswith('/admin/'):
            return self.get_response(request)

        if request.path.startswith('/static/'):
            return self.get_response(request)

        profile = getattr(request.user, 'profile', None)

        if profile and not profile.servername:
            if request.path not in allowed_paths:
                return redirect('complete_profile')

        return self.get_response(request)
