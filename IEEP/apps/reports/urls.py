from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('low-stock/', views.LowStockReportView.as_view(), name='low-stock-report'),
]
