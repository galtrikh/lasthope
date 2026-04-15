# from django.db import models
# from django.contrib.auth import get_user_model

# User = get_user_model()

# class Room(models.Model):
#     name = models.CharField(max_length=255, verbose_name='Название комнаты')
#     created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
#     updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
#     sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages', verbose_name='Отправитель сообщений из этой комнаты')
#     receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages', verbose_name='Получатель сообщений из этой комнаты')

#     def __str__(self):
#         return self.name
    
#     class Meta:
#         verbose_name = "Комната"
#         verbose_name_plural = "Комнаты"

# class Message(models.Model):
#     room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages', verbose_name='Комната')
#     sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages_in_room', verbose_name='Отправитель')
#     content = models.TextField(verbose_name='Содержание сообщения')
#     timestamp = models.DateTimeField(auto_now_add=True, verbose_name='Дата и время отправки')
#     is_read = models.BooleanField(default=False, verbose_name='Прочитано')

#     def __str__(self):
#         return f'Message from {self.sender} in {self.room} at {self.timestamp}'
    
#     class Meta:
#         verbose_name = "Сообщение"
#         verbose_name_plural = "Сообщения"
