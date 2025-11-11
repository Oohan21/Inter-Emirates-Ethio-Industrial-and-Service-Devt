# procurement/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Supplier URLs
    path('suppliers/', views.SupplierListView.as_view(), name='supplier-list'),
    path('suppliers/create/', views.SupplierCreateView.as_view(), name='supplier-create'),
    path('suppliers/<int:pk>/', views.SupplierDetailView.as_view(), name='supplier-detail'),
    path('suppliers/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier-edit'),
    
    # Purchase Order URLs
    path('purchase-orders/', views.PurchaseOrderListView.as_view(), name='purchase-order-list'),
    path('purchase-orders/<int:pk>/', views.PurchaseOrderDetailView.as_view(), name='purchase-order-detail'),
    path('purchase-orders/create/', views.PurchaseOrderCreateView.as_view(), name='purchase-order-create'),
    path('purchase-orders/<int:pk>/send/', views.PurchaseOrderSendView.as_view(), name='purchase-order-send'),
    path('purchase-orders/<int:pk>/edit/', views.PurchaseOrderUpdateView.as_view(), name='purchase-order-edit'),
    
    # Requisition URLs
    path('requisitions/', views.PurchaseRequisitionListView.as_view(), name='requisition-list'),
    path('requisitions/<int:pk>/', views.PurchaseRequisitionDetailView.as_view(), name='requisition-detail'),
    path('requisitions/create/', views.PurchaseRequisitionCreateView.as_view(), name='requisition-create'),
    
    # Goods Receipt URLs
    path('goods-receipts/', views.GoodsReceiptListView.as_view(), name='goods-receipt-list'),
    path('goods-receipts/<int:pk>/', views.GoodsReceiptDetailView.as_view(), name='goods-receipt-detail'),
    path('goods-receipts/create/', views.GoodsReceiptCreateView.as_view(), name='goods-receipt-create'),
]