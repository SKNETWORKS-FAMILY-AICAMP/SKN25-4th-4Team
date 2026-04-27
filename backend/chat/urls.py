from django.urls import path
from . import views

urlpatterns = [
    path('sessions/', views.ChatSessionListView.as_view(), name='session-list'),
    path('sessions/<int:session_id>/', views.ChatSessionDetailView.as_view(), name='session-detail'),
    path('sessions/<int:session_id>/messages/', views.MessageListView.as_view(), name='message-list'),
    path('ask/', views.AskView.as_view(), name='ask'),
    path('ask/stream/', views.AskStreamView.as_view(), name='ask-stream'),
    path('health/', views.HealthView.as_view(), name='health'),
]