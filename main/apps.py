from django.apps import AppConfig

class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        """Вызывается когда приложение готово"""
        import sys
        
        # Запускаем планировщик только в основном процессе runserver
        # Не запускаем в: migrations, shell, test, и в reloader процессе
        if (
            'runserver' not in sys.argv or 
            '--noreload' in sys.argv or
            'migrate' in sys.argv or 
            'makemigrations' in sys.argv or
            'shell' in sys.argv or
            'test' in sys.argv
        ):
            return
        
        # Проверяем, что это не дочерний процесс autoreloader
        if os.environ.get('RUN_MAIN') != 'true':
            return
        
        try:
            from .scheduler import start_scheduler
            start_scheduler()
            print('✓ Планировщик статистики запущен')
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Ошибка запуска планировщика: {e}')

import os