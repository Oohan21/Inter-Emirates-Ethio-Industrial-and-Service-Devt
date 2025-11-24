# sales/urls.py
from django.urls import path
from . import views



urlpatterns = [
    # Customer URLs
    path('customers/', views.CustomerListView.as_view(), name='customer-list'),
    path('customers/create/', views.CustomerCreateView.as_view(), name='customer-create'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer-detail'),
    path('customers/<int:pk>/edit/', views.CustomerUpdateView.as_view(), name='customer-update'),
    path('customers/<int:pk>/toggle-active/', views.CustomerToggleActiveView.as_view(), name='customer-toggle-active'),
    
    # Sales Inquiry URLs
    path('inquiries/', views.SalesInquiryListView.as_view(), name='sales-inquiry-list'),
    path('inquiries/create/', views.SalesInquiryCreateView.as_view(), name='sales-inquiry-create'),
    path('inquiries/<int:pk>/', views.SalesInquiryDetailView.as_view(), name='sales-inquiry-detail'),
    path('inquiries/<int:pk>/edit/', views.SalesInquiryUpdateView.as_view(), name='sales-inquiry-update'),
    path('inquiries/<int:pk>/submit/', views.SalesInquirySubmitView.as_view(), name='sales-inquiry-submit'),
    path('inquiries/<int:pk>/check-inventory/', views.CheckInventoryView.as_view(), name='check-inventory'),
    path('inquiries/<int:pk>/approve/', views.ApproveInquiryView.as_view(), name='approve-inquiry'),
    path('inquiries/<int:pk>/cancel/', views.SalesInquiryCancelView.as_view(), name='sales-inquiry-cancel'),
    
    # Sale Order URLs
    path('orders/', views.SaleOrderListView.as_view(), name='sale-order-list'),
    path('orders/create/', views.SaleOrderCreateView.as_view(), name='sale-order-create'),
    path('orders/<int:pk>/', views.SaleOrderDetailView.as_view(), name='sale-order-detail'),
    path('orders/<int:pk>/edit/', views.SaleOrderUpdateView.as_view(), name='sale-order-update'),
    path('orders/<int:pk>/confirm/', views.SaleOrderConfirmView.as_view(), name='sale-order-confirm'),
    path('orders/<int:pk>/ship/', views.SaleOrderShipView.as_view(), name='sale-order-ship'),
    path('orders/<int:pk>/deliver/', views.SaleOrderDeliverView.as_view(), name='sale-order-deliver'),
    path('orders/<int:pk>/cancel/', views.SaleOrderCancelView.as_view(), name='sale-order-cancel'),
    path('orders/<int:pk>/create-invoice/', views.CreateInvoiceView.as_view(), name='create-invoice'),
    
    # AJAX URLs
    path('ajax/customer-search/', views.customer_search_ajax, name='customer-search-ajax'),
    path('ajax/product-search/', views.product_search_ajax, name='product-search-ajax'),
    path('ajax/stock-check/', views.stock_check_ajax, name='stock-check-ajax'),
    
    # Dashboard
    path('', views.SalesDashboardView.as_view(), name='sales-dashboard'),
]