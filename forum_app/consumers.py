# consumers.py - WebSocket consumer для форума

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


class ForumTopicConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer для обновлений темы форума в реальном времени
    """
    
    async def connect(self):
        """Подключение к WebSocket"""
        self.topic_id = self.scope['url_route']['kwargs']['topic_id']
        self.room_group_name = f'topic_{self.topic_id}'
        
        # Проверяем права доступа к теме
        can_access = await self.check_topic_access()
        if not can_access:
            await self.close()
            return
        
        # Присоединяемся к группе
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Отправляем приветственное сообщение
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Подключено к теме'
        }))
    
    async def disconnect(self, close_code):
        """Отключение от WebSocket"""
        # Покидаем группу
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        """
        Получение сообщений от клиента
        (для будущих функций типа "пользователь печатает...")
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'typing':
                # Уведомляем других что пользователь печатает
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_typing',
                        'user': data.get('user'),
                    }
                )
        except json.JSONDecodeError:
            pass
    
    # Обработчики событий от channel layer
    
    async def new_post(self, event):
        """Новый пост в теме"""
        await self.send(text_data=json.dumps({
            'type': 'new_post',
            'post_id': event['post_id'],
            'author': event['author'],
            'content_preview': event['content_preview'],
        }))
    
    async def update_likes(self, event):
        """Обновление лайков"""
        await self.send(text_data=json.dumps({
            'type': 'update_likes',
            'post_id': event['post_id'],
            'likes_count': event['likes_count'],
        }))
    
    async def post_edited(self, event):
        """Пост отредактирован"""
        await self.send(text_data=json.dumps({
            'type': 'post_edited',
            'post_id': event['post_id'],
            'content': event['content'],
        }))
    
    async def post_deleted(self, event):
        """Пост удален"""
        await self.send(text_data=json.dumps({
            'type': 'post_deleted',
            'post_id': event['post_id'],
        }))
    
    async def user_typing(self, event):
        """Пользователь печатает"""
        await self.send(text_data=json.dumps({
            'type': 'user_typing',
            'user': event['user'],
        }))
    
    async def user_online(self, event):
        """Пользователь онлайн"""
        await self.send(text_data=json.dumps({
            'type': 'user_online',
            'user_id': event['user_id'],
            'online': event['online'],
        }))
    
    @database_sync_to_async
    def check_topic_access(self):
        """Проверка доступа к теме"""
        from forum_app.models import ForumTopic
        
        try:
            topic = ForumTopic.objects.get(id=self.topic_id)
            user = self.scope['user']
            
            # Если пользователь не авторизован
            if isinstance(user, AnonymousUser):
                return not topic.category.require_auth
            
            # Дополнительные проверки прав можно добавить здесь
            return True
        except ForumTopic.DoesNotExist:
            return False


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer для личных уведомлений пользователя
    """
    
    async def connect(self):
        """Подключение к личным уведомлениям"""
        user = self.scope['user']
        
        # Только для авторизованных пользователей
        if isinstance(user, AnonymousUser):
            await self.close()
            return
        
        self.user_group_name = f'user_{user.id}'
        
        # Присоединяемся к личной группе
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Отправляем количество непрочитанных уведомлений
        unread_count = await self.get_unread_count()
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'unread_count': unread_count
        }))
    
    async def disconnect(self, close_code):
        """Отключение"""
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Получение сообщений от клиента"""
        try:
            data = json.loads(text_data)
            
            if data.get('type') == 'mark_read':
                notification_id = data.get('notification_id')
                await self.mark_notification_read(notification_id)
        except json.JSONDecodeError:
            pass
    
    # Обработчики событий
    
    async def new_notification(self, event):
        """Новое уведомление"""
        await self.send(text_data=json.dumps({
            'type': 'new_notification',
            'notification_id': event['notification_id'],
            'title': event['title'],
            'message': event['message'],
            'url': event.get('url'),
            'created_at': event['created_at'],
        }))
    
    async def notification_read(self, event):
        """Уведомление прочитано"""
        await self.send(text_data=json.dumps({
            'type': 'notification_read',
            'notification_id': event['notification_id'],
        }))
    
    @database_sync_to_async
    def get_unread_count(self):
        """Получить количество непрочитанных уведомлений"""
        # Здесь должна быть ваша модель уведомлений
        # from notifications.models import Notification
        # return Notification.objects.filter(
        #     user=self.scope['user'],
        #     is_read=False
        # ).count()
        return 0  # Заглушка
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """Пометить уведомление как прочитанное"""
        # from notifications.models import Notification
        # try:
        #     notification = Notification.objects.get(
        #         id=notification_id,
        #         user=self.scope['user']
        #     )
        #     notification.is_read = True
        #     notification.save()
        # except Notification.DoesNotExist:
        #     pass
        pass  # Заглушка
