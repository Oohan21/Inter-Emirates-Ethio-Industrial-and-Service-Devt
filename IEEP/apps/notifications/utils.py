# notifications/utils.py
from django.http import JsonResponse
import json
from django.contrib.auth import get_user_model
from .models import Notification

def create_notification_safe(user, title, message, notification_type='system', priority='medium', action_url=None):
    """
    Safely create a notification ensuring the user is a User instance
    """
    User = get_user_model()
    
    # Convert user ID to User instance if needed
    if isinstance(user, int):
        try:
            user = User.objects.get(pk=user)
        except User.DoesNotExist:
            return None
    
    # Ensure user is a User instance
    if not isinstance(user, User):
        return None
    
    # Create the notification
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        priority=priority,
        action_url=action_url
    )

def send_browser_notification(request, notification_data):
    """
    Fallback method to send notifications via AJAX polling
    when WebSockets are not available
    """
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        # Store notification in session for AJAX polling
        if 'pending_notifications' not in request.session:
            request.session['pending_notifications'] = []
        
        request.session['pending_notifications'].append(notification_data)
        request.session.modified = True
        
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

def get_pending_notifications(request):
    """Get pending notifications for AJAX polling"""
    notifications = request.session.get('pending_notifications', [])
    request.session['pending_notifications'] = []
    request.session.modified = True
    return notifications