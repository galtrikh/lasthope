# from django.shortcuts import render
# from django.contrib.auth.decorators import login_required
# from .models import Room, Message
# from .forms import MessageForm

# @login_required
# def chats_list(request):
#     rooms = Room.objects.filter(sender=request.user) | Room.objects.filter(receiver=request.user)
#     return render(request, 'rtchat/chats.html', {'rooms': rooms})

# @login_required
# def chat(request):
#     form = MessageForm()
#     room = Room.objects.filter(id=request.GET.get('room_id')).first()
#     messages = Message.objects.filter(room=room).order_by('timestamp') if room else []
#     context = {
#         'form': form,
#         'room': room,
#         'messages': messages
#     }
#     return render(request, 'rtchat/chat.html', context)