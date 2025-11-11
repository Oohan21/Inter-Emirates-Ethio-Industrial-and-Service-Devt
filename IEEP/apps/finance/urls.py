# finance/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('transactions/', views.TransactionListView.as_view(), name='transaction-list'),
    path('cost-calculations/', views.CostCalculationListView.as_view(), name='cost-calculation-list'),
    path('invoices/', views.InvoiceListView.as_view(), name='invoice-list'),
]