from django.urls import path
from . import views

urlpatterns = [
    path('warehouses/', views.WarehouseListView.as_view(), name='warehouse-list'),
    path('warehouses/add/', views.WarehouseCreateView.as_view(), name='warehouse-add'),
    path('warehouses/<int:pk>/edit/', views.WarehouseUpdateView.as_view(), name='warehouse-edit'),
    path('warehouses/<int:pk>/delete/', views.WarehouseDeleteView.as_view(), name='warehouse-delete'),
    path('stock-items/', views.StockItemListView.as_view(), name='stock-item-list'),
    path('stock-items/add/', views.StockItemCreateView.as_view(), name='stock-item-add'),
    path('stock-items/<int:pk>/', views.StockItemDetailView.as_view(), name='stock-item-detail'),
    path('stock-items/<int:pk>/print-label/', views.PrintLabelView.as_view(), name='print-label'),
    path('stock-items/<int:pk>/stock-count/', views.StockCountCreateView.as_view(), name='stock-count-create'),
    path('stock-items/<int:pk>/quality-check/', views.QualityCheckCreateView.as_view(), name='quality-check-create'),
    path('stock-transaction/', views.StockTransactionCreateView.as_view(), name='stock-transaction-create'),
    path('stock-adjustment/', views.StockAdjustmentCreateView.as_view(), name='stock-adjustment-create'),
    path('transactions/', views.StockTransactionListView.as_view(), name='transaction-list'),
    path('low-stock/', views.LowStockListView.as_view(), name='low-stock-list'),
    path('orders/create/', views.OrderCreateView.as_view(), name='order-create'),
    path('orders/', views.OrderListView.as_view(), name='order-list'),

    # ----- AJAX endpoints -----
    path('ajax/adjust/', views.stock_adjustment_ajax, name='stock-adjustment-ajax'),
    path('ajax/create-po/', views.order_create_ajax, name='order-create-ajax'),
    
    # API Views (JSON)
    path('api/low-stock/', views.LowStockAPIView.as_view(), name='api-low-stock'),
    path('api/dashboard-data/', views.DashboardDataAPIView.as_view(), name='api-dashboard-data'),
    path('api/procurement-update/', views.ProcurementUpdateAPIView.as_view(), name='api-procurement-update'),
    
]
