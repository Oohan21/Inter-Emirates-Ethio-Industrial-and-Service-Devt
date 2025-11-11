# production/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # HTML Views
    path('work-orders/', views.WorkOrderListView.as_view(), name='work-order-list'),
    path('work-orders/<int:pk>/', views.WorkOrderDetailView.as_view(), name='work-order-detail'),
    path('work-orders/create/', views.WorkOrderCreateView.as_view(), name='work-order-create'),
    path('work-orders/<int:pk>/update/', views.WorkOrderUpdateView.as_view(), name='work-order-update'),
    path('work-orders/<int:pk>/start/', views.StartProductionView.as_view(), name='work-order-start'),
    path('work-orders/<int:pk>/complete/', views.CompleteProductionView.as_view(), name='work-order-complete'),
    path('work-orders/<int:pk>/add-log/', views.AddProductionLogView.as_view(), name='work-order-add-log'),
    path('work-orders/<int:pk>/report/', views.WorkOrderReportView.as_view(), name='work-order-report'),
    path('production-board/', views.ProductionBoardView.as_view(), name='production-board'),
    
    # API Views
    path('api/work-orders/', views.WorkOrderAPIView.as_view(), name='api-work-orders'),
    path('api/dashboard/', views.ProductionDashboardView.as_view(), name='api-production-dashboard'),
    
    # Action Views
    path('material-issue/create/', views.MaterialIssueCreateView.as_view(), name='material-issue-create'),
    path('downtime/create/', views.DowntimeCreateView.as_view(), name='downtime-create'),
    path('quality-check/create/', views.QualityCheckCreateView.as_view(), name='quality-check-create'),
]