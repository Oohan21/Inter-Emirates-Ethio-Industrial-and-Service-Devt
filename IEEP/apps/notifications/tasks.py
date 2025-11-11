# notifications/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Notification, NotificationPreference
import logging
from .models import Notification
from apps.inventory.models import StockItem
from apps.maintenance.models import Asset
from apps.production.models import ProductionOrder
from apps.quality.models import QCRecord
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)

@shared_task
def check_low_stock():
    """Check for low stock items and create notifications"""
    low_stock_items = StockItem.objects.filter(
        quantity__lte=models.F('reorder_threshold'),
        quantity__gt=0
    )
    
    for item in low_stock_items:
        Notification.objects.create(
            user=item.warehouse.manager, 
            title='Low Stock Alert',
            message=f'Product {item.product.sku} is below reorder level in {item.warehouse.code}',
            notification_type='low_stock',
            priority='high',
            related_object_type='StockItem',
            related_object_id=str(item.id)
        )
        
        # Send email if user prefers
        preferences = NotificationPreference.objects.filter(user=item.warehouse.manager).first()
        if preferences and preferences.email_notifications and preferences.low_stock_alerts:
            send_mail(
                'Low Stock Alert - Inter Emirates ERP',
                f'Product {item.product.sku} ({item.product.name}) is below reorder level.\n'
                f'Current quantity: {item.quantity}\n'
                f'Reorder threshold: {item.reorder_threshold}\n'
                f'Warehouse: {item.warehouse.code}',
                'noreply@interemirates.com',
                [item.warehouse.manager.email],
                fail_silently=True,
            )

@shared_task
def create_low_stock_notification(stock_item_id: int):
    try:
        item = StockItem.objects.select_related(
            'product', 'warehouse', 'warehouse__manager'
        ).get(id=stock_item_id)
    except StockItem.DoesNotExist:
        return

    if not item.is_low_stock:
        return

    manager = item.warehouse.manager
    if not manager:
        return

    url = reverse('stock-item-detail', kwargs={'pk': item.id})
    notif = Notification.objects.create(
        user=manager,
        title=f"Low Stock: {item.product.sku}",
        message=f"{item.product.name} in {item.warehouse.code} is low ({item.quantity} left).",
        notification_type='low_stock',
        priority='high',
        action_url=url
    )

    try:
        pref = manager.notificationpreference
        if pref.email_notifications and pref.low_stock_alerts:
            send_mail(
                subject=f"[URGENT] Low Stock – {item.product.sku}",
                message=(
                    f"Product: {item.product.name}\n"
                    f"SKU: {item.product.sku}\n"
                    f"Current: {item.quantity} {item.product.unit_of_measure}\n"
                    f"Threshold: {item.reorder_threshold}\n"
                    f"Warehouse: {item.warehouse.name}\n\n"
                    f"View: {settings.BASE_URL}{url}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[manager.email],
                fail_silently=False,
            )
    except Exception as e:
        logger.warning(f"Email failed for low stock {item.id}: {e}")

    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            "notifications",
            {
                "type": "low_stock_alert",
                "notification": {
                    "id": notif.id,
                    "title": notif.title,
                    "message": notif.message,
                    "url": notif.action_url,
                    "priority": notif.priority,
                }
            }
        )

    item.mark_alert_sent()

@shared_task
def check_overdue_maintenance():
    """Check for overdue maintenance tasks"""
    today = timezone.now().date()
    overdue_assets = Asset.objects.filter(
        next_maintenance_date__lt=today,
        status='operational'
    )
    
    for asset in overdue_assets:
        # Create notification for maintenance engineers
        maintenance_users = User.objects.filter(role__name='maintenance_engineer')
        for user in maintenance_users:
            Notification.objects.create(
                user=user,
                title='Overdue Maintenance',
                message=f'Asset {asset.asset_code} has overdue maintenance',
                notification_type='overdue_maintenance',
                priority='high',
                related_object_type='Asset',
                related_object_id=str(asset.id)
            )

@shared_task
def check_late_work_orders():
    """Check for late work orders"""
    today = timezone.now()
    late_orders = ProductionOrder.objects.filter(
        scheduled_end__lt=today,
        status__in=['planned', 'in_progress']
    )
    
    for order in late_orders:
        Notification.objects.create(
            user=order.created_by,
            title='Late Work Order',
            message=f'Work order {order.order_number} is behind schedule',
            notification_type='late_work_order',
            priority='medium',
            related_object_type='ProductionOrder',
            related_object_id=str(order.id)
        )

# notifications/tasks.py - ADD THESE TASKS
@shared_task
def check_overdue_tickets():
    """Check for overdue tickets and escalate if necessary"""
    overdue_tickets = Ticket.objects.filter(
        due_date__lt=timezone.now(),
        status__in=['open', 'in_progress']
    )
    
    for ticket in overdue_tickets:
        # Notify assignee and manager
        users_to_notify = set()
        if ticket.assigned_to:
            users_to_notify.add(ticket.assigned_to)
        if ticket.assigned_department and ticket.assigned_department.manager:
            users_to_notify.add(ticket.assigned_department.manager)
        
        for user in users_to_notify:
            Notification.objects.create(
                user=user,
                title=f"OVERDUE TICKET: {ticket.ticket_number}",
                message=f"Ticket '{ticket.title}' is overdue. Due: {ticket.due_date.strftime('%Y-%m-%d')}",
                notification_type='system',
                priority='urgent',
                action_url=reverse('ticket-detail', kwargs={'pk': ticket.pk})
            )

@shared_task
def auto_close_resolved_tickets():
    """Automatically close tickets that have been resolved for more than 7 days"""
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=7)
    resolved_tickets = Ticket.objects.filter(
        status='resolved',
        resolved_at__lt=cutoff_date
    )
    
    for ticket in resolved_tickets:
        ticket.status = 'closed'
        ticket.closed_at = timezone.now()
        ticket.save()
        
        # Notify creator
        Notification.objects.create(
            user=ticket.created_by,
            title=f"Ticket Closed: {ticket.ticket_number}",
            message=f"Your ticket '{ticket.title}' has been automatically closed after 7 days in resolved status.",
            notification_type='system',
            priority='low'
        )

@shared_task
def send_ticket_digest():
    """Send daily digest of ticket statistics to managers"""
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    
    departments = Department.objects.filter(is_active=True)
    
    for department in departments:
        department_tickets = Ticket.objects.filter(assigned_department=department)
        open_tickets = department_tickets.filter(status__in=['open', 'in_progress'])
        overdue_tickets = open_tickets.filter(due_date__lt=timezone.now())
        
        if department.manager and open_tickets.exists():  # UPDATED: Direct manager access
            context = {
                'department': department,
                'total_tickets': department_tickets.count(),
                'open_tickets': open_tickets.count(),
                'overdue_tickets': overdue_tickets.count(),
                'tickets': open_tickets[:10]  # Top 10 tickets
            }
            
            html_content = render_to_string('notifications/email/ticket_digest.html', context)
            text_content = render_to_string('notifications/email/ticket_digest.txt', context)
            
            email = EmailMultiAlternatives(
                subject=f"Daily Ticket Digest - {department.name}",
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[department.manager.email]
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=True)