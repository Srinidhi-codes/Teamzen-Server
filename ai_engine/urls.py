from django.urls import path
from .views import (
    PolicyQAView, 
    PolicyFileListCreateView, 
    PolicyFileRetrieveUpdateDestroyView, 
    SmartAssistantChatView,
    AIConfigurationView
)

urlpatterns = [
    path('ask-policy/', PolicyQAView.as_view(), name='ask_policy'),
    path('chat/', SmartAssistantChatView.as_view(), name='smart_chat'),
    path('policies/', PolicyFileListCreateView.as_view(), name='policy_list_create'),
    path('policies/<int:pk>/', PolicyFileRetrieveUpdateDestroyView.as_view(), name='policy_detail'),
    path('ai-config/', AIConfigurationView.as_view(), name='ai_config'),
]
