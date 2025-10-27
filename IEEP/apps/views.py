from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.generic import ListView,
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, F, Sum, Count
from django.db import transaction
from django.utils import timezone
from .models import Order, OrderItem, Warehouse, StockItem, StockTransaction, ReorderAlert
from apps.products.models import Product, Category
from .forms import StockAdjustmentForm
from django.views import View
from django import forms
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
import json
import csv
from django.urls import reverse_lazy

class WarehouseListView(LoginRequiredMixin, ListView):
    model = Warehouse
    template_name = 'inventory/warehouse_list.html'
    context_object_name = 'warehouses'
    
    def get_queryset(self):
        return Warehouse.objects.filter(is_active=True).prefetch_related('stock_items')

class StockItemListView(LoginRequiredMixin, ListView):
    model = StockItem
    template_name = 'inventory/stock_item_list.html'
    context_object_name = 'stock_items'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = StockItem.objects.select_related('product__unit_of_measure', 'warehouse')
        
        # Fetch summary statistics
        self.total_items = queryset.count()
        self.total_value = sum(float(item.total_value) for item in queryset)
        self.low_stock_count = queryset.filter(quantity__lte=F('reorder_threshold')).count()
        self.out_of_stock_count = queryset.filter(quantity__lte=0).count()
        self.reorder_alert_count = ReorderAlert.objects.filter(status='active').count()
      
        # Apply sorting
        sort = self.request.GET.get('sort', 'product__sku')
        if sort.startswith('-'):
            queryset = queryset.order_by(f'-{sort[1:]}')
        else:
            queryset = queryset.order_by(sort)
        
        return queryset
    
    def get(self, request, *args, **kwargs):
        if request.GET.get('export') == 'csv':
            queryset = self.get_queryset()
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="stock_items.csv"'
            writer = csv.writer(response)
            writer.writerow(['SKU', 'Name', 'Batch Number', 'Warehouse', 'Location', 'Quantity', 'Unit', 'Value', 'Status', 'Procurement', 'Expiry', 'Created At', 'Updated At'])
            for item in queryset:
                status = 'Out of Stock' if item.quantity <= 0 else 'Low Stock' if item.is_low_stock else 'In Stock'
                expiry = 'Expired' if item.is_expired else 'Near Expiry' if item.expiry_date and item.expiry_date <= timezone.now().date() + timezone.timedelta(days=30) else item.expiry_date or '-'
                writer.writerow([
                    item.product.sku,
                    item.product.name,
                    item.batch_number or '-',
                    item.warehouse.code,
                    item.location or 'Main',
                    item.quantity,
                    item.product.unit_of_measure.symbol,
                    item.total_value,
                    status,
                    item.get_procurement_status_display(),
                    expiry,
                    item.created_at,
                    item.updated_at
                ])
            return response
        return super().get(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'warehouses': Warehouse.objects.filter(is_active=True),
            'categories': Category.objects.all(),
            'total_items': self.total_items,
            'total_value': self.total_value,
            'low_stock_count': self.low_stock_count,
            'out_of_stock_count': self.out_of_stock_count,
            'reorder_alert_count': self.reorder_alert_count,
            'product_types': Product.objects.values('product_type').distinct(),
            'procurement_statuses': [choice[0] for choice in StockItem._meta.get_field('procurement_status').choices],
            'current_filters': self.request.GET.urlencode(),
        })
        return context


