# inventory/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('warehouses/', views.WarehouseListView.as_view(), name='warehouse-list'),
    path('warehouses/add/', views.WarehouseCreateView.as_view(), name='warehouse-add'),
    path('warehouses/<int:pk>/edit/', views.WarehouseUpdateView.as_view(), name='warehouse-edit'),
    path('warehouses/<int:pk>/delete/', views.WarehouseDeleteView.as_view(), name='warehouse-delete'),
    path('stock-items/', views.StockItemListView.as_view(), name='stock-item-list'),
    path('stock-items/add/', views.StockItemCreateView.as_view(), name='stock-item-add'),
    path('stock-items/<int:pk>/edit/', views.StockItemUpdateView.as_view(), name='stock-item-edit'),
    path('stock-items/<int:pk>/delete/', views.StockItemDeleteView.as_view(), name='stock-item-delete'),
    path('stock-items/<int:pk>/', views.StockItemDetailView.as_view(), name='stock-item-detail'),
    path('low-stock/', views.LowStockListView.as_view(), name='low-stock-list'),
    path('procurement-status/', views.ProcurementStatusView.as_view(), name='procurement-status'),
    path('low-stock/create-requisition/', views.LowStockToRequisitionView.as_view(), name='low-stock-create-requisition'),
    path('low-stock/auto-reorder/', views.AutoReorderView.as_view(), name='low-stock-auto-reorder'),
    path('low-stock/analysis/', views.LowStockAnalysisView.as_view(), name='low-stock-analysis'),
    path('orders/create/', views.OrderCreateView.as_view(), name='order-create'),
    path('orders/', views.OrderListView.as_view(), name='order-list'),
    path('orders/<int:pk>/', views.OrderDetailView.as_view(), name='order-detail'),
    path('orders/<int:pk>/edit/', views.OrderUpdateView.as_view(), name='order-edit'),
    path('orders/<int:pk>/delete/', views.OrderDeleteView.as_view(), name='order-delete'),
    path('orders/<int:pk>/confirm/', views.OrderConfirmView.as_view(), name='order-confirm'),
    path('stock-items/<int:pk>/print-label/', views.PrintLabelView.as_view(), name='print-label'),
    path('stock-items/<int:pk>/stock-count/', views.StockCountCreateView.as_view(), name='stock-count-create'),
    path('stock-items/<int:pk>/quality-check/', views.QualityCheckCreateView.as_view(), name='quality-check-create'),
    path('inquiries/', views.InventoryInquiryListView.as_view(), name='inventory-inquiry-list'),
    path('inquiries/<int:pk>/', views.InventoryInquiryDetailView.as_view(), name='inventory-inquiry-detail'),
    path('inquiries/<int:pk>/check/', views.CheckInventoryView.as_view(), name='inventory-check-inquiry'),

    # Transaction management
    path('transactions/', views.StockTransactionListView.as_view(), name='transactions-list'),
    path('transactions/<int:pk>/', views.StockTransactionDetailView.as_view(), name='transaction-detail'),
    path('transactions/adjust/', views.StockAdjustmentCreateView.as_view(), name='stock-adjustment-create'),
    path('transactions/transfer/', views.StockTransferCreateView.as_view(), name='stock-transfer-create'),
    path('transactions/in/', views.StockInCreateView.as_view(), name='stock-in-create'),
    path('transactions/export/', views.TransactionExportView.as_view(), name='transaction-export'),
    
    # Quick action endpoints
    path('inquiries/<int:pk>/approve/', views.ApproveInquiryView.as_view(), name='inventory-approve-inquiry'),
    path('inquiries/<int:pk>/reject/', views.RejectInquiryView.as_view(), name='inventory-reject-inquiry'),
    
    # ----- AJAX endpoints -----
    path('ajax/adjust/', views.stock_adjustment_ajax, name='stock-adjustment-ajax'),
    path('ajax/quick-adjust/', views.QuickStockAdjustmentView.as_view(), name='quick-stock-adjust'),
    path('ajax/create-po/', views.order_create_ajax, name='order-create-ajax'),
    path('orders/<int:order_id>/items/add/', views.OrderItemCreateView.as_view(), name='order-item-add'),
    path('orders/<int:order_id>/items/<int:item_id>/update/', views.OrderItemUpdateView.as_view(), name='order-item-update'),
    path('orders/<int:order_id>/items/<int:item_id>/delete/', views.OrderItemDeleteView.as_view(), name='order-item-delete'),

    # API Views (JSON)
    path('api/low-stock/', views.LowStockAPIView.as_view(), name='api-low-stock'),
    path('api/dashboard-data/', views.DashboardDataAPIView.as_view(), name='api-dashboard-data'),
    path('api/procurement-update/', views.ProcurementUpdateAPIView.as_view(), name='api-procurement-update'),
    path('api/stock-availability/', views.stock_availability_api, name='stock-availability-api'),
    path('api/bulk-stock-check/', views.bulk_stock_check_api, name='bulk-stock-check-api'),
    path('api/get-stock-items/', views.get_stock_items_ajax, name='get-stock-items-api'),
]