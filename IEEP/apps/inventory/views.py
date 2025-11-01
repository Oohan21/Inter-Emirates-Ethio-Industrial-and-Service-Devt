from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.generic import ListView
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
        self.low_stock_count = queryset.filter(
        quantity__gt=0,
        quantity__lte=F('reorder_threshold')
        ).count()
        self.out_of_stock_count = queryset.filter(quantity__lte=0).count()
        self.reorder_alert_count = ReorderAlert.objects.filter(status='active').count()

        # Apply filters
        warehouse = self.request.GET.get('warehouse')
        if warehouse:
            queryset = queryset.filter(warehouse_id=warehouse)
        
        product_type = self.request.GET.get('product_type')
        if product_type:
            queryset = queryset.filter(product__product_type=product_type)
        
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(product__category_id=category)
        
        stock_status = self.request.GET.get('stock_status')
        if stock_status == 'low':
            queryset = queryset.filter(quantity__lte=F('reorder_threshold'), quantity__gt=0)
        elif stock_status == 'out':
            queryset = queryset.filter(quantity__lte=0)
        elif stock_status == 'normal':
            queryset = queryset.filter(quantity__gt=F('reorder_threshold'))
        
        procurement_status = self.request.GET.get('procurement_status')
        if procurement_status:
            queryset = queryset.filter(procurement_status=procurement_status)
        
        expiry_status = self.request.GET.get('expiry_status')
        if expiry_status == 'expired':
            queryset = queryset.filter(expiry_date__lt=timezone.now().date())
        elif expiry_status == 'near_expiry':
            queryset = queryset.filter(
                expiry_date__gte=timezone.now().date(),
                expiry_date__lte=timezone.now().date() + timezone.timedelta(days=30)
            )
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(product__sku__icontains=search) |
                Q(product__name__icontains=search) |
                Q(batch_number__icontains=search) |
                Q(location__icontains=search) |
                Q(notes__icontains=search)
            )
        
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
        stock_items = self.get_queryset()
        stock_status = stock_items.aggregate(
            in_stock=Count('id',
                filter=~Q(quantity__lte=F('reorder_threshold')) & ~Q(quantity__lte=0)),
            low_stock=Count('id',
                filter=Q(quantity__lte=F('reorder_threshold')) & ~Q(quantity__lte=0)),
            out_of_stock=Count('id',
                filter=Q(quantity__lte=0))
        )
        context['stock_status'] = stock_status
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

class LowStockListView(LoginRequiredMixin, ListView):
    model = StockItem
    template_name = 'inventory/low_stock_list.html'
    context_object_name = 'low_stock_items'
    ordering = ['product__sku']

    def get_queryset(self):
        """
        Returns only items that are LOW STOCK (0 < qty <= reorder_threshold).
        Uses product.reorder_threshold as fallback if StockItem threshold is 0.
        """
        return (
            StockItem.objects
            .select_related('product__unit_of_measure', 'warehouse')
            .annotate(
                effective_threshold=Coalesce(
                    F('reorder_threshold'),
                    F('product__reorder_threshold'),
                    Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
                ),
                stock_deficit=F('effective_threshold') - F('quantity')
            )
            .filter(
                quantity__gt=0,                         
                quantity__lte=F('effective_threshold') 
            )
            .order_by('stock_deficit')  
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = context['low_stock_items']

        context['total_low_stock'] = items.count()
        context['total_deficit'] = sum(
            float(item.stock_deficit) for item in items
        )
        context['total_value_at_risk'] = sum(
            float(item.total_value) for item in items
        )

        return context

