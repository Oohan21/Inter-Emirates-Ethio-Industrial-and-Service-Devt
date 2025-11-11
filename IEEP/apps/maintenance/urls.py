# maintenance/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # HTML Views
    path('assets/', views.AssetListView.as_view(), name='asset-list'),
    path('assets/<int:pk>/', views.AssetDetailView.as_view(), name='asset-detail'),
    path('assets/create/', views.AssetCreateView.as_view(), name='asset-create'),
    path('assets/<int:pk>/update/', views.AssetUpdateView.as_view(), name='asset-update'),
    path('maintenance-orders/', views.MaintenanceOrderListView.as_view(), name='maintenance-order-list'),
    path('maintenance-orders/<int:pk>/', views.MaintenanceOrderDetailView.as_view(), name='maintenance-order-detail'),
    path('maintenance-orders/create/', views.MaintenanceOrderCreateView.as_view(), name='maintenance-order-create'),
    path('maintenance-orders/<int:pk>/update/', views.MaintenanceOrderUpdateView.as_view(), name='maintenance-order-update'),
    path('upcoming/', views.UpcomingMaintenanceView.as_view(), name='upcoming-maintenance'),
    path('dashboard/', views.MaintenanceDashboardView.as_view(), name='maintenance-dashboard'),
    path('calendar/', views.MaintenanceCalendarView.as_view(), name='maintenance-calendar'),
    
    # API Views
    path('api/maintenance-orders/', views.MaintenanceAPIView.as_view(), name='api-maintenance-orders'),
    path('api/upcoming-maintenance/', views.UpcomingMaintenanceAPIView.as_view(), name='api-upcoming-maintenance'),
    path('api/assets/', views.AssetAPIView.as_view(), name='api-assets'),
    path('api/trigger-checks/', views.TriggerMaintenanceCheckView.as_view(), name='trigger-maintenance-checks'),
]