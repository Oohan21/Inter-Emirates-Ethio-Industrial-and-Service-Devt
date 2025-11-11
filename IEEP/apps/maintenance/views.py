from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Count
from django.utils import timezone
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from .models import Asset, MaintenanceOrder, MaintenanceLog, SparePartUsage
from .forms import AssetForm, MaintenanceOrderForm, AssetCreateForm  
from apps.notifications.utils import create_notification_safe
from .tasks import check_maintenance_schedules, check_overdue_maintenance_orders


class AssetListView(LoginRequiredMixin, ListView):
    model = Asset
    template_name = 'maintenance/asset_list.html'
    context_object_name = 'assets'
    
    def get_queryset(self):
        return Asset.objects.all().order_by('asset_code')

class AssetDetailView(LoginRequiredMixin, DetailView):
    model = Asset
    template_name = "maintenance/asset_detail.html"
    context_object_name = "asset"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        asset = self.get_object()
        
        try:
            # Get maintenance orders for this asset
            context["maintenance_orders"] = MaintenanceOrder.objects.filter(
                asset=asset
            ).select_related('assigned_to').order_by("-created_at")[:10]
            
            # Get maintenance logs for this asset with proper related fields
            context["maintenance_logs"] = MaintenanceLog.objects.filter(
                maintenance_order__asset=asset
            ).select_related('created_by', 'technician', 'maintenance_order').order_by("-created_at")[:10]
            
            # Get upcoming maintenance
            context["upcoming_maintenance"] = MaintenanceOrder.objects.filter(
                asset=asset,
                status__in=["requested", "approved", "in_progress"]
            ).select_related('assigned_to').order_by("scheduled_date")
            
            # Add today's date for template comparisons
            context["today"] = timezone.now().date()
            
        except Exception as e:
            # Handle any errors gracefully
            context["maintenance_orders"] = []
            context["maintenance_logs"] = []
            context["upcoming_maintenance"] = []
            
        return context

class AssetCreateView(LoginRequiredMixin, CreateView):
    model = Asset
    form_class = AssetCreateForm  # Use the simplified create form
    template_name = 'maintenance/asset_form.html'
    
    def get_success_url(self):
        return reverse_lazy('asset-detail', kwargs={'pk': self.object.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create New Asset'
        context['is_create'] = True
        return context
    
    def form_valid(self, form):
        # Set default values for optional fields if needed
        if not form.instance.maintenance_interval_days:
            form.instance.maintenance_interval_days = 30
        return super().form_valid(form)
        
class AssetUpdateView(LoginRequiredMixin, UpdateView):
    model = Asset
    form_class = AssetForm
    template_name = 'maintenance/asset_form.html'
    
    def get_success_url(self):
        return reverse_lazy('asset-detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit {self.object.name}'
        return context

class MaintenanceOrderListView(LoginRequiredMixin, ListView):
    model = MaintenanceOrder
    template_name = 'maintenance/maintenance_order_list.html'
    context_object_name = 'maintenance_orders'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = MaintenanceOrder.objects.select_related('asset')
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by priority
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        # Filter by search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search) |
                Q(asset__asset_code__icontains=search) |
                Q(asset__name__icontains=search)
            )
        
        return queryset.order_by('-created_at')

class MaintenanceOrderDetailView(LoginRequiredMixin, DetailView):
    model = MaintenanceOrder
    template_name = 'maintenance/maintenance_order_detail.html'
    context_object_name = 'order'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['maintenance_logs'] = MaintenanceLog.objects.filter(
            maintenance_order=self.object
        ).select_related('created_by', 'technician').order_by('-created_at')
        context['spare_parts'] = SparePartUsage.objects.filter(
            maintenance_order=self.object
        ).select_related('product', 'stock_item').order_by('-used_at')
        return context

class MaintenanceOrderCreateView(LoginRequiredMixin, CreateView):
    model = MaintenanceOrder
    form_class = MaintenanceOrderForm
    template_name = 'maintenance/maintenance_order_form.html'
    
    def form_valid(self, form):
        form.instance.requested_by = self.request.user
        response = super().form_valid(form)
        
        # Send notification for new maintenance order
        if form.instance.priority in ['high', 'urgent']:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            maintenance_users = User.objects.filter(groups__name='maintenance_team')
            
            for user in maintenance_users:
                create_notification_safe(
                    user=user,
                    title=f"NEW MAINTENANCE ORDER: {self.object.order_number}",
                    message=f"New {form.instance.get_priority_display()} priority maintenance order created for {form.instance.asset.name}",
                    notification_type='maintenance_alert',
                    priority='high' if form.instance.priority == 'urgent' else 'medium',
                    action_url=reverse('maintenance-order-detail', kwargs={'pk': self.object.pk})
                )
        
        return response
    
    def get_success_url(self):
        return reverse_lazy('maintenance-order-detail', kwargs={'pk': self.object.pk})

class MaintenanceOrderUpdateView(LoginRequiredMixin, UpdateView):
    model = MaintenanceOrder
    form_class = MaintenanceOrderForm
    template_name = 'maintenance/maintenance_order_form.html'
    
    def form_valid(self, form):
        old_status = self.object.status
        old_assigned_to = self.object.assigned_to
        
        # Create maintenance log for status changes
        if 'status' in form.changed_data:
            MaintenanceLog.objects.create(
                maintenance_order=self.object,
                action='status_updated',
                notes=f"Status changed from {self.object.status} to {form.cleaned_data['status']}",
                created_by=self.request.user
            )
        
        response = super().form_valid(form)
        
        # Send notifications for important changes
        if 'status' in form.changed_data:
            self.notify_status_change(old_status, form.cleaned_data['status'])
        
        if 'assigned_to' in form.changed_data and form.cleaned_data['assigned_to']:
            self.notify_assignment(form.cleaned_data['assigned_to'])
        
        return response
    
    def notify_status_change(self, old_status, new_status):
        """Notify relevant users about status changes"""
        users_to_notify = set()
        
        # Notify requester
        if self.object.requested_by:
            users_to_notify.add(self.object.requested_by)
        
        # Notify assigned technician
        if self.object.assigned_to:
            users_to_notify.add(self.object.assigned_to)
        
        # Notify maintenance team for important status changes
        if new_status in ['completed', 'cancelled']:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            maintenance_users = User.objects.filter(groups__name='maintenance_team')
            users_to_notify.update(maintenance_users)
        
        for user in users_to_notify:
            if user != self.request.user:  # Don't notify the user making the change
                create_notification_safe(
                    user=user,
                    title=f"MAINTENANCE STATUS UPDATE: {self.object.order_number}",
                    message=f"Maintenance order for {self.object.asset.name} changed from {old_status} to {new_status}",
                    notification_type='maintenance_update',
                    priority='medium',
                    action_url=reverse('maintenance-order-detail', kwargs={'pk': self.object.pk})
                )
    
    def notify_assignment(self, assigned_user):
        """Notify user about assignment"""
        create_notification_safe(
            user=assigned_user,
            title=f"MAINTENANCE ASSIGNMENT: {self.object.order_number}",
            message=f"You have been assigned to maintenance order for {self.object.asset.name}",
            notification_type='maintenance_assignment',
            priority='medium',
            action_url=reverse('maintenance-order-detail', kwargs={'pk': self.object.pk})
        )
    
    def get_success_url(self):
        return reverse_lazy('maintenance-order-detail', kwargs={'pk': self.object.pk})

class UpcomingMaintenanceView(LoginRequiredMixin, ListView):
    model = MaintenanceOrder
    template_name = 'maintenance/upcoming_maintenance.html'
    context_object_name = 'upcoming_maintenance'
    
    def get_queryset(self):
        # Get orders that are not completed and have due dates
        queryset = MaintenanceOrder.objects.filter(
            status__in=['requested', 'in_progress']
        ).select_related('asset').order_by('scheduled_date')
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        
        # Calculate statistics
        today = timezone.now().date()
        week_from_now = today + timezone.timedelta(days=7)
        
        context['upcoming_count'] = queryset.count()
        context['due_this_week'] = queryset.filter(
            scheduled_date__lte=week_from_now,
            scheduled_date__gte=today
        ).count()
        context['high_priority'] = queryset.filter(priority='high').count()
        context['overdue'] = queryset.filter(scheduled_date__lt=today).count()
        
        return context

# API Views
@method_decorator(login_required, name='dispatch')
class MaintenanceAPIView(View):
    def get(self, request):
        try:
            maintenance_orders = MaintenanceOrder.objects.select_related('asset').all()
            
            data = {
                'success': True,
                'count': maintenance_orders.count(),
                'maintenance_orders': [
                    {
                        'id': order.id,
                        'order_number': order.order_number,
                        'asset_code': order.asset.asset_code,
                        'asset_name': order.asset.name,
                        'priority': order.priority,
                        'status': order.status,
                        'maintenance_type': order.maintenance_type,
                        'scheduled_date': order.scheduled_date.isoformat() if order.scheduled_date else None,
                        'created_at': order.created_at.isoformat(),
                    }
                    for order in maintenance_orders
                ]
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

@method_decorator(login_required, name='dispatch')
class UpcomingMaintenanceAPIView(View):
    def get(self, request):
        try:
            today = timezone.now().date()
            week_from_now = today + timezone.timedelta(days=7)
            
            upcoming_orders = MaintenanceOrder.objects.filter(
                status__in=['requested', 'in_progress'],
                scheduled_date__gte=today
            ).select_related('asset').order_by('scheduled_date')
            
            data = {
                'success': True,
                'count': upcoming_orders.count(),
                'upcoming_maintenance': [
                    {
                        'id': order.id,
                        'order_number': order.order_number,
                        'asset_code': order.asset.asset_code,
                        'asset_name': order.asset.name,
                        'priority': order.priority,
                        'status': order.status,
                        'scheduled_date': order.scheduled_date.isoformat() if order.scheduled_date else None,
                        'days_until_due': (order.scheduled_date - today).days if order.scheduled_date else None,
                        'is_overdue': order.scheduled_date < today if order.scheduled_date else False,
                    }
                    for order in upcoming_orders
                ]
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

@method_decorator(login_required, name='dispatch')
class AssetAPIView(View):
    def get(self, request):
        try:
            assets = Asset.objects.all()
            
            data = {
                'success': True,
                'count': assets.count(),
                'assets': [
                    {
                        'id': asset.id,
                        'asset_code': asset.asset_code,
                        'name': asset.name,
                        'asset_type': asset.asset_type,
                        'status': asset.status,
                        'location': asset.location,
                        'last_maintenance': asset.last_maintenance.isoformat() if asset.last_maintenance else None,
                        'next_maintenance': asset.next_maintenance.isoformat() if asset.next_maintenance else None,
                        'total_operating_hours': float(asset.total_operating_hours),
                    }
                    for asset in assets
                ]
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

class MaintenanceDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        # Get statistics for dashboard
        total_assets = Asset.objects.count()
        active_orders = MaintenanceOrder.objects.filter(status__in=['requested', 'in_progress']).count()
        completed_orders = MaintenanceOrder.objects.filter(status='completed').count()
        
        # Get assets by status
        assets_by_status = Asset.objects.values('status').annotate(count=Count('id'))
        
        # Get upcoming maintenance
        upcoming_maintenance = MaintenanceOrder.objects.filter(
            status__in=['requested', 'in_progress']
        ).select_related('asset').order_by('scheduled_date')[:5]
        
        context = {
            'total_assets': total_assets,
            'active_orders': active_orders,
            'completed_orders': completed_orders,
            'assets_by_status': assets_by_status,
            'upcoming_maintenance': upcoming_maintenance,
        }
        
        return render(request, 'maintenance/dashboard.html', context)

class MaintenanceCalendarView(LoginRequiredMixin, View):
    def get(self, request):
        maintenance_orders = MaintenanceOrder.objects.select_related('asset').filter(
            scheduled_date__isnull=False
        )
        
        calendar_events = []
        for order in maintenance_orders:
            calendar_events.append({
                'title': f"{order.order_number} - {order.asset.asset_code}",
                'start': order.scheduled_date.isoformat(),
                'url': reverse_lazy('maintenance-order-detail', kwargs={'pk': order.id}),
                'className': f"priority-{order.priority}",
            })
        
        context = {
            'calendar_events': calendar_events,
        }
        
        return render(request, 'maintenance/calendar.html', context)

# maintenance/views.py - ADD THIS VIEW
class TriggerMaintenanceCheckView(LoginRequiredMixin, View):
    """API endpoint to manually trigger maintenance checks"""
    
    def post(self, request):
        try:
            from .tasks import (
                check_maintenance_schedules, 
                check_overdue_maintenance_orders,
                check_high_priority_orders,
                check_resource_shortages
            )
            
            # Run checks asynchronously
            check_maintenance_schedules.delay()
            check_overdue_maintenance_orders.delay()
            check_high_priority_orders.delay()
            check_resource_shortages.delay()
            
            return JsonResponse({
                'success': True,
                'message': 'Maintenance checks triggered successfully'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)