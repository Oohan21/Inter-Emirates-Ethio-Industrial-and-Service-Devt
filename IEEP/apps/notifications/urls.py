# notifications/urls.py - COMPLETE UPDATED VERSION
from django.urls import path
from . import views

urlpatterns = [
    # Existing notification URLs
    path('', views.NotificationListView.as_view(), name='notification-list'),
    path('<int:pk>/mark-read/', views.MarkNotificationReadView.as_view(), name='mark-notification-read'),
    path('mark-all-read/', views.MarkAllNotificationsReadView.as_view(), name='mark-all-read'),
    path('<int:pk>/delete/', views.DeleteNotificationView.as_view(), name='delete-notification'),
    path('unread-count/', views.UnreadNotificationCountView.as_view(), name='unread-count'),
    path('preferences/', views.NotificationPreferencesView.as_view(), name='notification-preferences'),
    path('pending/', views.PendingNotificationsView.as_view(), name='pending-notifications'),
    
    # Ticketing System URLs - FIXED URL PATTERNS
    path('tickets/', views.TicketListView.as_view(), name='ticket-list'),
    path('tickets/create/', views.TicketCreateView.as_view(), name='ticket-create'),
    path('tickets/<int:pk>/', views.TicketDetailView.as_view(), name='ticket-detail'),
    path('tickets/<int:pk>/update/', views.TicketUpdateView.as_view(), name='ticket-update'),
    path('tickets/<int:ticket_id>/add-message/', views.AddTicketMessageView.as_view(), name='add-ticket-message'),
    
    # Internal Messaging URLs
    path('messages/send/', views.InternalMessageCreateView.as_view(), name='message-send'),
    path('messages/inbox/', views.MessageInboxView.as_view(), name='message-inbox'),
    path('messages/outbox/', views.MessageOutboxView.as_view(), name='message-outbox'),
    path('messages/<int:pk>/', views.MessageDetailView.as_view(), name='message-detail'),
    path('messages/<int:pk>/reply/', views.ReplyToMessageView.as_view(), name='message-reply'),
    path('messages/<int:pk>/read/', views.MarkMessageReadView.as_view(), name='mark-message-read'),
    path('messages/<int:pk>/confirm/', views.ConfirmMessageView.as_view(), name='confirm-message'),
    
    # API endpoints
    path('api/tickets/stats/', views.TicketStatsAPIView.as_view(), name='api-ticket-stats'),
    path('api/tickets/autocomplete/', views.TicketAutoCompleteView.as_view(), name='api-ticket-autocomplete'),
    path('api/tickets/bulk-update/', views.BulkTicketUpdateView.as_view(), name='api-ticket-bulk-update'),
    path('api/users/autocomplete/', views.UserAutoCompleteView.as_view(), name='api-user-autocomplete'),
    path('api/messages/unread-count/', views.UnreadMessageCountView.as_view(), name='api-unread-messages'),
    path('api/departments/<int:department_id>/tickets/', views.DepartmentTicketsAPIView.as_view(), name='api-department-tickets'),
    path('api/departments/tickets/', views.DepartmentTicketsAPIView.as_view(), name='api-all-departments-tickets'),
]