from django.urls import path
from . import views

urlpatterns = [
    path('chat/', views.ChatView.as_view(), name='chat_view'),
    path('api/chat/suggestions/', views.SuggestionView.as_view(), name='chat_suggestions'),
    path('api/chat/send/', views.SendMessageView.as_view(), name='chat_send'),
]