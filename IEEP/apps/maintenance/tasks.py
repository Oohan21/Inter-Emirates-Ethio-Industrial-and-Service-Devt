# maintenance/tasks.py - CREATE THIS FILE
from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from .models import Asset, MaintenanceOrder
from apps.notifications.utils import create_notification_safe
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)

@shared_task
def check_maintenance_schedules():
    """Check for assets requiring maintenance"""
    try:
        User = get_user_model()
        today = timezone.now().date()
        
        # Find assets with overdue maintenance
        overdue_assets = Asset.objects.filter(
            next_maintenance__lt=today,
            status='operational'
        )
        
        for asset in overdue_assets:
            # Notify maintenance team
            maintenance_users = User.objects.filter(groups__name='maintenance_team')
            if not maintenance_users.exists():
                maintenance_users = User.objects.filter(is_staff=True)
            
            for user in maintenance_users:
                create_notification_safe(
                    user=user,
                    title=f"OVERDUE MAINTENANCE: {asset.asset_code}",
                    message=f"Asset {asset.name} has overdue maintenance since {asset.next_maintenance}",
                    notification_type='overdue_maintenance',
                    priority='high',
                    action_url=reverse('asset-detail', kwargs={'pk': asset.pk})
                )
            
            logger.info(f"Notified about overdue maintenance for asset {asset.asset_code}")
        
        # Find assets with upcoming maintenance (within 7 days)
        next_week = today + timezone.timedelta(days=7)
        upcoming_assets = Asset.objects.filter(
            next_maintenance__range=[today, next_week],
            status='operational'
        )
        
        for asset in upcoming_assets:
            maintenance_users = User.objects.filter(groups__name='maintenance_team')
            if not maintenance_users.exists():
                maintenance_users = User.objects.filter(is_staff=True)
            
            for user in maintenance_users:
                create_notification_safe(
                    user=user,
                    title=f"Upcoming Maintenance: {asset.asset_code}",
                    message=f"Asset {asset.name} requires maintenance on {asset.next_maintenance}",
                    notification_type='maintenance_reminder',
                    priority='medium',
                    action_url=reverse('asset-detail', kwargs={'pk': asset.pk})
                )
        
        return f"Checked {overdue_assets.count()} overdue and {upcoming_assets.count()} upcoming maintenance tasks"
    
    except Exception as e:
        logger.error(f"Error in check_maintenance_schedules: {e}")
        return f"Error: {e}"

@shared_task
def check_overdue_maintenance_orders():
    """Check for overdue maintenance orders"""
    try:
        User = get_user_model()
        today = timezone.now().date()
        
        overdue_orders = MaintenanceOrder.objects.filter(
            scheduled_date__lt=today,
            status__in=['requested', 'in_progress']
        ).select_related('asset', 'assigned_to')
        
        for order in overdue_orders:
            users_to_notify = []
            
            # Notify assigned technician
            if order.assigned_to:
                users_to_notify.append(order.assigned_to)
            
            # Also notify maintenance supervisor
            supervisors = User.objects.filter(groups__name='maintenance_supervisor')
            users_to_notify.extend(supervisors)
            
            # If no specific users, notify maintenance team
            if not users_to_notify:
                maintenance_users = User.objects.filter(groups__name='maintenance_team')
                users_to_notify.extend(maintenance_users)
            
            for user in set(users_to_notify):
                create_notification_safe(
                    user=user,
                    title=f"OVERDUE MAINTENANCE ORDER: {order.order_number}",
                    message=f"Maintenance order for {order.asset.name} is overdue. Scheduled: {order.scheduled_date}",
                    notification_type='overdue_maintenance',
                    priority='urgent',
                    action_url=reverse('maintenance-order-detail', kwargs={'pk': order.pk})
                )
            
            logger.info(f"Notified about overdue maintenance order {order.order_number}")
        
        return f"Checked {overdue_orders.count()} overdue maintenance orders"
    
    except Exception as e:
        logger.error(f"Error in check_overdue_maintenance_orders: {e}")
        return f"Error: {e}"

@shared_task
def check_high_priority_orders():
    """Check for high priority maintenance orders that need attention"""
    try:
        User = get_user_model()
        
        high_priority_orders = MaintenanceOrder.objects.filter(
            priority__in=['high', 'urgent'],
            status='requested'
        ).select_related('asset')
        
        for order in high_priority_orders:
            # Notify maintenance team about high priority orders
            maintenance_users = User.objects.filter(groups__name='maintenance_team')
            
            for user in maintenance_users:
                create_notification_safe(
                    user=user,
                    title=f"HIGH PRIORITY MAINTENANCE: {order.order_number}",
                    message=f"High priority maintenance order for {order.asset.name} requires attention",
                    notification_type='maintenance_alert',
                    priority='high',
                    action_url=reverse('maintenance-order-detail', kwargs={'pk': order.pk})
                )
        
        return f"Checked {high_priority_orders.count()} high priority orders"
    
    except Exception as e:
        logger.error(f"Error in check_high_priority_orders: {e}")
        return f"Error: {e}"

@shared_task
def check_asset_health():
    """Check asset health and notify about potential issues"""
    try:
        User = get_user_model()
        
        # Find assets with potential issues
        problematic_assets = Asset.objects.filter(
            Q(status='needs_attention') |
            Q(status='under_maintenance') |
            Q(total_operating_hours__gt=10000)  # Example threshold
        )
        
        for asset in problematic_assets:
            # Notify maintenance team about asset health issues
            maintenance_users = User.objects.filter(groups__name='maintenance_team')
            supervisors = User.objects.filter(groups__name='maintenance_supervisor')
            
            for user in list(maintenance_users) + list(supervisors):
                create_notification_safe(
                    user=user,
                    title=f"ASSET HEALTH ALERT: {asset.asset_code}",
                    message=f"Asset {asset.name} requires attention. Status: {asset.get_status_display()}",
                    notification_type='asset_health',
                    priority='medium',
                    action_url=reverse('asset-detail', kwargs={'pk': asset.pk})
                )
        
        return f"Checked {problematic_assets.count()} assets for health issues"
    
    except Exception as e:
        logger.error(f"Error in check_asset_health: {e}")
        return f"Error: {e}"

# maintenance/tasks.py - ADD THIS TASK
@shared_task
def check_resource_shortages():
    """Check for resource shortages that might affect maintenance"""
    try:
        from apps.inventory.models import StockItem
        
        # Check for low stock of common maintenance parts
        low_stock_items = StockItem.objects.filter(
            quantity__lte=models.F('reorder_threshold'),
            product__category__name__icontains='maintenance'
        )
        
        for item in low_stock_items:
            # Notify maintenance supervisor and inventory manager
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            supervisors = User.objects.filter(groups__name='maintenance_supervisor')
            inventory_managers = User.objects.filter(groups__name='inventory_manager')
            
            for user in list(supervisors) + list(inventory_managers):
                create_notification_safe(
                    user=user,
                    title=f"MAINTENANCE PART SHORTAGE: {item.product.name}",
                    message=f"Maintenance part {item.product.name} is low on stock. Current: {item.quantity}, Threshold: {item.reorder_threshold}",
                    notification_type='resource_shortage',
                    priority='high',
                    action_url=reverse('stock-item-detail', kwargs={'pk': item.pk})
                )
        
        return f"Checked {low_stock_items.count()} maintenance parts for shortages"
    
    except Exception as e:
        logger.error(f"Error in check_resource_shortages: {e}")
        return f"Error: {e}"