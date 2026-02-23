# # main/scheduler.py

# from apscheduler.schedulers.background import BackgroundScheduler
# from apscheduler.jobstores.base import JobLookupError
# from django.core.management import call_command
# import logging
# import threading

# logger = logging.getLogger(__name__)

# _scheduler = None
# _lock = threading.Lock()


# def update_server_stats_job():
#     """Задача обновления статистики — защита от параллельного запуска"""
#     try:
#         call_command('update_server_stats')
#     except Exception as e:
#         logger.error(f'Ошибка обновления статистики: {e}')


# def start_scheduler():
#     global _scheduler
    
#     with _lock:
#         if _scheduler is not None and _scheduler.running:
#             logger.warning('Планировщик уже запущен, пропускаем')
#             return _scheduler
        
#         _scheduler = BackgroundScheduler(
#             job_defaults={
#                 'max_instances': 1,       # Только одна копия задачи одновременно
#                 'misfire_grace_time': 60, # Если задача пропущена, ждём 60 сек
#                 'coalesce': True,         # Объединяем пропущенные запуски в один
#             }
#         )
        
#         _scheduler.add_job(
#             update_server_stats_job,
#             'interval',
#             minutes=5,
#             id='update_server_stats',
#             replace_existing=True,
#         )
        
#         _scheduler.start()
#         logger.info('✓ Планировщик запущен (интервал: 5 минут)')
        
#         return _scheduler


# def stop_scheduler():
#     global _scheduler
    
#     with _lock:
#         if _scheduler and _scheduler.running:
#             _scheduler.shutdown(wait=False)
#             _scheduler = None
#             logger.info('Планировщик остановлен')