from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404, render
from datetime import timedelta
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import get_user_model
from django.db import models
from django.views.generic import (
    ListView,
    DetailView,
    TemplateView,
    CreateView,
    UpdateView,
    DeleteView,
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import (
    Q,
    F,
    Sum,
    Count,
    FloatField,
    Value,
    Case,
    When,
    DecimalField,
)
from decimal import Decimal
from django.contrib.messages.views import SuccessMessageMixin
from django.utils import timezone
from django.db import transaction
from .services.finance_integration import FinanceIntegrationService
from .services.procurement_integration import ProcurementIntegrationService
from .models import (
    Order,
    OrderItem,
    Warehouse,
    StockItem,
    StockTransaction,
    ReorderAlert,
)
from .forms import StockAdjustmentForm, StockItemForm, WarehouseForm, StockInForm, StockTransferForm
from apps.products.models import Product, Category
from apps.procurement.models import PurchaseRequisition, PurchaseOrder
from apps.sales.models import SalesInquiry
from django.views import View
from django import forms
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
import json
import csv
import uuid
import logging
import traceback
from django.urls import reverse_lazy, reverse
from django.db.models.functions import Coalesce
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)
User = get_user_model()


class StockItemCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = StockItem
    form_class = StockItemForm
    template_name = "inventory/stock_item_form.html"
    success_url = reverse_lazy("stock-item-list")
    success_message = "Stock item added successfully."

    def form_valid(self, form):
        response = super().form_valid(form)
        # Create initial transaction
        StockTransaction.objects.create(
            stock_item=self.object,
            transaction_type="adjustment",
            quantity=self.object.quantity,
            reference="Initial Stock",
            notes="Initial stock addition",
            created_by=self.request.user,
        )
        messages.success(self.request, self.success_message)
        return response


class StockItemUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = StockItem
    form_class = StockItemForm
    template_name = "inventory/stock_item_form.html"
    success_url = reverse_lazy("stock-item-list")
    success_message = "Stock item updated successfully."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_update"] = True
        return context

    def form_valid(self, form):
        # Get the original quantity before saving
        original_quantity = self.get_object().quantity
        response = super().form_valid(form)

        # If quantity changed, create a transaction
        if original_quantity != self.object.quantity:
            quantity_difference = self.object.quantity - original_quantity
            StockTransaction.objects.create(
                stock_item=self.object,
                transaction_type="adjustment",
                quantity=quantity_difference,
                reference="Manual Edit",
                notes=f"Stock item edited - quantity changed from {original_quantity} to {self.object.quantity}",
                created_by=self.request.user,
            )

        messages.success(self.request, self.success_message)
        return response


class WarehouseListView(LoginRequiredMixin, ListView):
    model = Warehouse
    template_name = "inventory/warehouse_list.html"
    context_object_name = "warehouses"

    def get_queryset(self):
        # Prefetch related stock items to avoid N+1 queries
        return (
            Warehouse.objects.filter(is_active=True)
            .prefetch_related("stock_items", "stock_items__product", "manager")
            .order_by("code")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        warehouses = context["warehouses"]

        # Calculate totals - FIXED LOGIC
        total_warehouses = warehouses.count()

        # Since we're only showing active warehouses in the queryset
        active_warehouses = total_warehouses

        # Calculate low stock and out of stock counts
        total_low_stock = 0
        total_out_of_stock = 0

        for warehouse in warehouses:
            total_low_stock += warehouse.low_stock_count
            total_out_of_stock += warehouse.out_of_stock_count

        context.update(
            {
                "total_warehouses": total_warehouses,
                "active_warehouses": active_warehouses,
                "total_low_stock": total_low_stock,
                "total_out_of_stock": total_out_of_stock,
            }
        )

        return context


class WarehouseCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = "inventory/warehouse_form.html"
    success_url = reverse_lazy("warehouse-list")
    success_message = "Warehouse created successfully."

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class WarehouseUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = "inventory/warehouse_form.html"
    success_url = reverse_lazy("warehouse-list")
    success_message = "Warehouse updated successfully."


class WarehouseDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Warehouse
    template_name = "inventory/warehouse_confirm_delete.html"
    success_url = reverse_lazy("warehouse-list")
    success_message = "Warehouse deleted successfully."

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        return super().delete(request, *args, **kwargs)


class StockItemListView(LoginRequiredMixin, ListView):
    model = StockItem
    template_name = 'inventory/stock_item_list.html'
    context_object_name = 'stock_items'
    paginate_by = 25

    def get_queryset(self):
        """Return the *filtered* queryset (NO pagination yet)"""
        qs = (
            StockItem.objects
            .select_related('product__unit_of_measure', 'warehouse', 'product')
            .only(
                'id', 'quantity', 'batch_number', 'location',
                'expiry_date', 'procurement_status',
                'created_at', 'updated_at',
                'product__sku', 'product__name',
                'product__unit_of_measure__symbol',
                'product__reorder_threshold',
                'warehouse__code'
            )
        )

        # ------------------- FILTERS -------------------
        warehouse = self.request.GET.get('warehouse')
        if warehouse:
            qs = qs.filter(warehouse_id=warehouse)

        product_type = self.request.GET.get('product_type')
        if product_type:
            qs = qs.filter(product__product_type=product_type)

        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(product__category_id=category)

        stock_status = self.request.GET.get('stock_status')
        if stock_status == 'low':
            qs = qs.filter(quantity__gt=0, quantity__lte=F('product__reorder_threshold'))
        elif stock_status == 'out':
            qs = qs.filter(quantity__lte=0)
        elif stock_status == 'normal':
            qs = qs.filter(quantity__gt=F('product__reorder_threshold'))

        procurement_status = self.request.GET.get('procurement_status')
        if procurement_status:
            qs = qs.filter(procurement_status=procurement_status)

        expiry_status = self.request.GET.get('expiry_status')
        if expiry_status == 'expired':
            qs = qs.filter(expiry_date__lt=timezone.now().date())
        elif expiry_status == 'near_expiry':
            near = timezone.now().date() + timezone.timedelta(days=30)
            qs = qs.filter(expiry_date__gte=timezone.now().date(),
                           expiry_date__lte=near)

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(product__sku__icontains=search) |
                Q(product__name__icontains=search) |
                Q(batch_number__icontains=search) |
                Q(location__icontains=search) |
                Q(notes__icontains=search)
            )

        sort = self.request.GET.get('sort', 'product__sku')
        if sort.startswith('-'):
            qs = qs.order_by(sort)
        else:
            qs = qs.order_by(sort)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        full_qs = self.get_queryset()
        total_items = full_qs.count()
        
        total_value = sum(float(item.total_value) for item in full_qs)

        low_stock_qs = full_qs.filter(
            quantity__gt=0,
            quantity__lte=F('product__reorder_threshold')
        )
        out_of_stock_qs = full_qs.filter(quantity__lte=0)

        low_stock_count = low_stock_qs.count()
        out_of_stock_count = out_of_stock_qs.count()

        stock_status = {
            'in_stock': full_qs.filter(
                quantity__gt=F('product__reorder_threshold')
            ).count(),
            'low_stock': low_stock_count,
            'out_of_stock': out_of_stock_count,
        }

        context.update({
            'stock_status': stock_status,
            'total_items': total_items,
            'total_value': total_value,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'reorder_alert_count': ReorderAlert.objects.filter(status='active').count(),
            'warehouses': Warehouse.objects.filter(is_active=True),
            'categories': Category.objects.all(),
            'product_type_choices': Product.PRODUCT_TYPES,
            'procurement_statuses': [
                c[0] for c in StockItem._meta.get_field('procurement_status').choices
            ],
            'current_filters': self.request.GET.urlencode(),
        })
        return context

    def get(self, request, *args, **kwargs):
        # ------------------- CSV EXPORT -------------------
        if request.GET.get('export') == 'csv':
            queryset = self.get_queryset()

            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="stock_items.csv"'

            writer = csv.writer(response)
            writer.writerow([
                'SKU', 'Name', 'Batch Number', 'Warehouse', 'Location',
                'Quantity', 'Unit', 'Value (ETB)', 'Status', 'Procurement',
                'Expiry', 'Created At', 'Updated At'
            ])

            for item in queryset:
                status = (
                    'Out of Stock' if item.quantity <= 0 else
                    'Low Stock' if item.quantity <= item.product.reorder_threshold else
                    'In Stock'
                )
                expiry = (
                    'Expired' if item.expiry_date and item.expiry_date < timezone.now().date() else
                    'Near Expiry' if item.expiry_date and
                                     item.expiry_date <= timezone.now().date() + timezone.timedelta(days=30)
                    else item.expiry_date or '-'
                )
                writer.writerow([
                    item.product.sku,
                    item.product.name,
                    item.batch_number or '-',
                    item.warehouse.code,
                    item.location or 'Main',
                    item.quantity,
                    item.product.unit_of_measure.symbol,
                    f"{item.total_value:.2f}",
                    status,
                    item.get_procurement_status_display(),
                    expiry,
                    item.created_at.strftime('%Y-%m-%d %H:%M'),
                    item.updated_at.strftime('%Y-%m-%d %H:%M'),
                ])
            return response

        return super().get(request, *args, **kwargs)

class StockItemDetailView(LoginRequiredMixin, DetailView):
    model = StockItem
    template_name = "inventory/stock_item_detail.html"
    context_object_name = "stock_item"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["warehouses"] = Warehouse.objects.filter(is_active=True)
        ctx["recent_transactions"] = self.object.transactions.order_by("-created_at")[
            :10
        ]
        return ctx

    def get_queryset(self):
        return StockItem.objects.select_related(
            "product", "warehouse"
        ).prefetch_related("transactions")

class StockItemDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            stock_item = get_object_or_404(StockItem, pk=pk)
            
            # Store info for message before deletion
            product_sku = stock_item.product.sku
            warehouse_code = stock_item.warehouse.code
            
            # Delete the stock item
            stock_item.delete()
            
            messages.success(request, f"Stock item {product_sku} from {warehouse_code} deleted successfully.")
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f"Stock item {product_sku} from {warehouse_code} deleted successfully."
                })
                
            return redirect('stock-item-list')
            
        except Exception as e:
            error_msg = f"Error deleting stock item: {str(e)}"
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': error_msg
                }, status=400)
            
            messages.error(request, error_msg)
            return redirect('stock-item-list')
            
# inventory/views.py - Transaction views
class StockTransactionListView(LoginRequiredMixin, ListView):
    model = StockTransaction
    template_name = "inventory/transaction_list.html"
    context_object_name = "transactions"
    paginate_by = 25
    
    def get_queryset(self):
        queryset = StockTransaction.objects.select_related(
            'stock_item__product',
            'stock_item__warehouse',
            'created_by',
            'destination_warehouse'
        ).order_by('-created_at')
        
        # Filter by transaction type
        transaction_type = self.request.GET.get('type')
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
        
        # Filter by date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        
        # Filter by warehouse
        warehouse = self.request.GET.get('warehouse')
        if warehouse:
            queryset = queryset.filter(
                models.Q(stock_item__warehouse_id=warehouse) |
                models.Q(destination_warehouse_id=warehouse)
            )
        
        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(stock_item__product__sku__icontains=search) |
                models.Q(stock_item__product__name__icontains=search) |
                models.Q(reference__icontains=search) |
                models.Q(notes__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transaction_types'] = StockTransaction.TRANSACTION_TYPES
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        
        # Summary statistics
        queryset = self.get_queryset()
        context['total_transactions'] = queryset.count()
        context['in_count'] = queryset.filter(transaction_type='in').count()
        context['out_count'] = queryset.filter(transaction_type='out').count()
        context['adjustment_count'] = queryset.filter(transaction_type='adjustment').count()
        context['transfer_count'] = queryset.filter(transaction_type='transfer').count()
        
        return context

class StockAdjustmentCreateView(LoginRequiredMixin, CreateView):
    model = StockTransaction
    form_class = StockAdjustmentForm
    template_name = "inventory/stock_adjustment.html"
    success_url = reverse_lazy('transaction-list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                messages.success(
                    self.request,
                    f"Stock adjusted successfully. New quantity: {form.instance.stock_item.quantity}"
                )
                return response
        except Exception as e:
            messages.error(self.request, f"Error adjusting stock: {str(e)}")
            return self.form_invalid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Adjust Stock"
        return context

class StockTransferCreateView(LoginRequiredMixin, CreateView):
    model = StockTransaction
    form_class = StockTransferForm
    template_name = "inventory/stock_transfer_form.html"
    success_url = reverse_lazy('transaction-list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                messages.success(
                    self.request,
                    f"Stock transferred successfully to {form.instance.destination_warehouse.name}"
                )
                return response
        except Exception as e:
            messages.error(self.request, f"Error transferring stock: {str(e)}")
            return self.form_invalid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Transfer Stock"
        return context

class StockInCreateView(LoginRequiredMixin, CreateView):
    model = StockTransaction
    form_class = StockInForm
    template_name = "inventory/stock_in_form.html"
    success_url = reverse_lazy('transaction-list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                messages.success(
                    self.request,
                    f"Stock added successfully. New quantity: {form.instance.stock_item.quantity}"
                )
                return response
        except Exception as e:
            messages.error(self.request, f"Error adding stock: {str(e)}")
            return self.form_invalid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Stock In"
        return context

@method_decorator(login_required, name='dispatch')
class QuickStockAdjustmentView(View):
    """AJAX endpoint for quick stock adjustments"""
    
    def post(self, request):
        # Check if it's JSON data first
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
        else:
            # For form data, use request.POST
            data = request.POST
        
        try:
            stock_item_id = data.get('stock_item_id')
            adjustment_type = data.get('adjustment_type', 'set')
            quantity = Decimal(data.get('quantity', 0))
            reference = data.get('reference', '')
            notes = data.get('notes', '')
            
            if not stock_item_id:
                return JsonResponse({'success': False, 'error': 'Stock item required'}, status=400)
            
            with transaction.atomic():
                stock_item = StockItem.objects.select_for_update().get(id=stock_item_id)
                current_quantity = stock_item.quantity
                
                # Calculate adjustment quantity
                if adjustment_type == 'set':
                    adjustment_quantity = quantity - current_quantity
                elif adjustment_type == 'add':
                    adjustment_quantity = quantity
                elif adjustment_type == 'subtract':
                    adjustment_quantity = -quantity
                else:
                    return JsonResponse({'success': False, 'error': 'Invalid adjustment type'}, status=400)
                
                # Validate adjustment
                new_quantity = current_quantity + adjustment_quantity
                if new_quantity < 0:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Adjustment would result in negative stock: {new_quantity}'
                    }, status=400)
                
                # Create transaction
                stock_transaction = StockTransaction.objects.create(
                    stock_item=stock_item,
                    transaction_type='adjustment',
                    quantity=adjustment_quantity,
                    reference=reference or f"Quick-ADJ-{timezone.now().strftime('%H%M%S')}",
                    notes=notes,
                    created_by=request.user,
                    previous_quantity=current_quantity,
                    new_quantity=new_quantity
                )
                
                return JsonResponse({
                    'success': True,
                    'message': 'Stock adjusted successfully',
                    'new_quantity': float(stock_item.quantity),
                    'transaction_id': stock_transaction.id
                })
                
        except StockItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Stock item not found'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

@method_decorator(login_required, name='dispatch')
class StockTransactionDetailView(DetailView):
    model = StockTransaction
    template_name = "inventory/transaction_detail.html"
    context_object_name = "transaction"
    
    def get_queryset(self):
        return StockTransaction.objects.select_related(
            'stock_item__product',
            'stock_item__warehouse',
            'created_by',
            'destination_warehouse'
        )

@method_decorator(login_required, name='dispatch')
class TransactionExportView(View):
    """Export transactions to CSV or Excel"""
    
    def get(self, request):
        format_type = request.GET.get('format', 'csv')
        transaction_type = request.GET.get('type', '')
        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')
        
        # Build queryset with same filters as list view
        queryset = StockTransaction.objects.select_related(
            'stock_item__product',
            'stock_item__warehouse',
            'created_by'
        ).order_by('-created_at')
        
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        
        if format_type == 'csv':
            return self.export_csv(queryset)
        else:
            return self.export_excel(queryset)
    
    def export_csv(self, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="stock_transactions.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Date', 'Type', 'Product SKU', 'Product Name', 'Warehouse', 
            'Quantity Change', 'Reference', 'Notes', 'Created By'
        ])
        
        for transaction in queryset:
            writer.writerow([
                transaction.created_at.strftime('%Y-%m-%d %H:%M'),
                transaction.get_transaction_type_display(),
                transaction.stock_item.product.sku,
                transaction.stock_item.product.name,
                transaction.stock_item.warehouse.code,
                transaction.quantity,
                transaction.reference or '',
                transaction.notes or '',
                transaction.created_by.get_full_name() or transaction.created_by.username
            ])
        
        return response
    
    def export_excel(self, queryset):
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="stock_transactions.xlsx"'
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Stock Transactions"
        
        # Headers
        headers = ['Date', 'Type', 'Product SKU', 'Product Name', 'Warehouse', 
                  'Quantity Change', 'Reference', 'Notes', 'Created By']
        ws.append(headers)
        
        # Data
        for transaction in queryset:
            ws.append([
                transaction.created_at.strftime('%Y-%m-%d %H:%M'),
                transaction.get_transaction_type_display(),
                transaction.stock_item.product.sku,
                transaction.stock_item.product.name,
                transaction.stock_item.warehouse.code,
                float(transaction.quantity),
                transaction.reference or '',
                transaction.notes or '',
                transaction.created_by.get_full_name() or transaction.created_by.username
            ])
        
        wb.save(response)
        return response

class LowStockListView(LoginRequiredMixin, ListView):
    model = StockItem
    template_name = "inventory/low_stock_list.html"
    context_object_name = "low_stock_items"
    ordering = ["product__sku"]

    def get_queryset(self):
        """
        Returns only items that are LOW STOCK (0 < qty <= product.reorder_threshold)
        """
        return (
            StockItem.objects.select_related("product__unit_of_measure", "warehouse")
            .filter(
                quantity__gt=0,  # Exclude out-of-stock
                quantity__lte=F(
                    "product__reorder_threshold"
                ),  # Below product's reorder level
            )
            .order_by("product__sku")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = context["low_stock_items"]
        context["warehouses"] = Warehouse.objects.filter(is_active=True)

        # Add procurement context
        context["can_create_requisition"] = context["low_stock_items"].exists()

        # Summary stats
        context["total_low_stock"] = items.count()
        context["total_deficit"] = sum(
            float(item.product.reorder_threshold - item.quantity) for item in items
        )
        context["total_value_at_risk"] = sum(float(item.total_value) for item in items)

        return context

    def post(self, request, *args, **kwargs):
        """Handle bulk requisition creation"""
        if "create_requisition" in request.POST:
            stock_item_ids = request.POST.getlist("stock_item_ids")

            if not stock_item_ids:
                messages.error(request, "Please select at least one stock item")
                return redirect("low-stock-list")

            try:
                low_stock_items = StockItem.objects.filter(
                    id__in=stock_item_ids, is_low_stock=True
                )

                requisition = (
                    ProcurementIntegrationService.create_requisition_from_low_stock(
                        low_stock_items=low_stock_items,
                        requested_by=request.user,
                        department="Inventory",
                    )
                )

                messages.success(
                    request,
                    f"Requisition {requisition.requisition_number} created successfully",
                )
                return redirect("procurement-status")

            except Exception as e:
                messages.error(request, f"Error creating requisition: {str(e)}")
                return redirect("low-stock-list")

        return super().get(request, *args, **kwargs)


class OrderCreateView(LoginRequiredMixin, View):
    template_name = "inventory/order_create.html"

    def get(self, request, *args, **kwargs):
        context = {
            "warehouses": Warehouse.objects.filter(is_active=True),
            "products": Product.objects.filter(is_active=True).select_related(
                "unit_of_measure"
            ),
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                # Handle both JSON and form submissions
                if request.content_type == "application/json":
                    data = json.loads(request.body)
                else:
                    data = request.POST

                # Validate required fields
                warehouse_id = data.get("warehouse")

                if not warehouse_id:
                    if request.content_type == "application/json":
                        return JsonResponse(
                            {"success": False, "error": "Warehouse is required"},
                            status=400,
                        )
                    else:
                        messages.error(request, "Warehouse is required")
                        return self.get(request)

                # Get warehouse
                try:
                    warehouse = Warehouse.objects.get(id=warehouse_id, is_active=True)
                except Warehouse.DoesNotExist:
                    if request.content_type == "application/json":
                        return JsonResponse(
                            {"success": False, "error": "Invalid warehouse"}, status=400
                        )
                    else:
                        messages.error(request, "Invalid warehouse")
                        return self.get(request)

                # Create order (order_number will be auto-generated)
                order = Order.objects.create(
                    warehouse=warehouse, created_by=request.user, status="pending"
                )

                # Process order items
                order_items_created = False

                if request.content_type == "application/json":
                    order_items = data.get("order_items", [])
                    for item_data in order_items:
                        self._create_order_item(order, item_data)
                        order_items_created = True
                else:
                    # Handle form submission
                    product_ids = request.POST.getlist("product_id")
                    quantities = request.POST.getlist("quantity")

                    for product_id, quantity in zip(product_ids, quantities):
                        if quantity and float(quantity) > 0:
                            self._create_order_item_from_form(
                                order, product_id, quantity
                            )
                            order_items_created = True

                # Validate that we have at least one order item
                if not order_items_created:
                    order.delete()  # Clean up empty order
                    if request.content_type == "application/json":
                        return JsonResponse(
                            {
                                "success": False,
                                "error": "At least one order item is required",
                            },
                            status=400,
                        )
                    else:
                        messages.error(request, "At least one order item is required")
                        return self.get(request)

                # For now, just create the order without auto-confirming
                # Users can confirm and update stock later through a separate action

                response_data = {
                    "success": True,
                    "message": f"Order {order.order_number} created successfully",
                    "order_id": order.id,
                    "order_number": order.order_number,
                }

                if request.content_type == "application/json":
                    return JsonResponse(response_data)
                else:
                    messages.success(request, response_data["message"])
                    return redirect("order-list")

        except Exception as e:
            error_msg = f"Error creating order: {str(e)}"
            if request.content_type == "application/json":
                return JsonResponse({"success": False, "error": error_msg}, status=500)
            else:
                messages.error(request, error_msg)
                return self.get(request)

    def _create_order_item(self, order, item_data):
        """Create order item from JSON data"""
        product_id = item_data.get("product_id")
        quantity = item_data.get("quantity")

        if not product_id or not quantity:
            raise ValueError("Product ID and quantity are required for order items")

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise ValueError(f"Invalid product ID: {product_id}")

        if float(quantity) <= 0:
            raise ValueError(f"Quantity must be positive for product {product.sku}")

        OrderItem.objects.create(order=order, product=product, quantity=quantity)

    def _create_order_item_from_form(self, order, product_id, quantity):
        """Create order item from form data"""
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise ValueError(f"Invalid product ID: {product_id}")

        if float(quantity) <= 0:
            raise ValueError(f"Quantity must be positive for product {product.sku}")

        OrderItem.objects.create(order=order, product=product, quantity=quantity)


class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = "inventory/order_list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        return Order.objects.select_related("warehouse", "created_by").order_by(
            "-created_at"
        )


class OrderDetailView(LoginRequiredMixin, DetailView):
    model = Order
    template_name = "inventory/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("warehouse", "created_by").prefetch_related(
            "order_items__product"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        context["order_items"] = order.order_items.select_related(
            "product__unit_of_measure"
        )
        context["total_quantity"] = sum(
            item.quantity for item in context["order_items"]
        )
        context["can_edit"] = order.status == "pending"
        context["can_delete"] = order.status == "pending"
        return context


class OrderUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Order
    template_name = "inventory/order_create.html"
    fields = ["warehouse"]
    success_message = "Order updated successfully."

    def get_success_url(self):
        return reverse("order-detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order_items"] = self.object.order_items.select_related(
            "product__unit_of_measure"
        )
        context["products"] = Product.objects.filter(is_active=True).select_related(
            "unit_of_measure"
        )
        context["warehouses"] = Warehouse.objects.filter(is_active=True)
        context["is_update"] = True
        context["order"] = self.object
        return context

    def form_valid(self, form):
        if self.object.status != "pending":
            messages.error(self.request, "Only pending orders can be edited.")
            return redirect("order-detail", pk=self.object.pk)

        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response

    def get_initial(self):
        initial = super().get_initial()
        initial["warehouse"] = self.object.warehouse.id
        return initial

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if self.object.status != "pending":
            messages.error(request, "Only pending orders can be edited.")
            return redirect("order-detail", pk=self.object.pk)

        # Handle order item updates
        product_ids = request.POST.getlist("product_id")
        quantities = request.POST.getlist("quantity")
        existing_items = request.POST.getlist("existing_items")

        try:
            with transaction.atomic():
                # Update existing items
                existing_item_ids = [
                    int(item_id) for item_id in existing_items if item_id
                ]
                current_items = {
                    item.id: item for item in self.object.order_items.all()
                }

                # Remove items that are no longer in the form
                for item_id in current_items:
                    if item_id not in existing_item_ids:
                        current_items[item_id].delete()

                # Update or create items
                for i, (product_id, quantity) in enumerate(
                    zip(product_ids, quantities)
                ):
                    if not product_id or not quantity:
                        continue

                    try:
                        product = Product.objects.get(id=product_id, is_active=True)
                        quantity = Decimal(quantity)

                        if quantity <= 0:
                            continue

                        # Check if this is an existing item (by position in the form)
                        if i < len(existing_items) and existing_items[i]:
                            item_id = int(existing_items[i])
                            if item_id in current_items:
                                # Update existing item
                                order_item = current_items[item_id]
                                order_item.product = product
                                order_item.quantity = quantity
                                order_item.save()
                            else:
                                # Create new item
                                OrderItem.objects.create(
                                    order=self.object,
                                    product=product,
                                    quantity=quantity,
                                )
                        else:
                            # Create new item
                            OrderItem.objects.create(
                                order=self.object, product=product, quantity=quantity
                            )

                    except (Product.DoesNotExist, ValueError, IndexError):
                        continue

                # Validate that we have at least one order item
                if not self.object.order_items.exists():
                    messages.error(request, "At least one order item is required.")
                    return self.form_invalid(form)

        except Exception as e:
            messages.error(request, f"Error updating order items: {str(e)}")
            return self.form_invalid(form)

        return super().post(request, *args, **kwargs)


class OrderDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Order
    template_name = "inventory/order_confirm_delete.html"
    success_url = reverse_lazy("order-list")
    success_message = "Order deleted successfully."

    def delete(self, request, *args, **kwargs):
        order = self.get_object()

        # Only allow deletion of pending orders
        if order.status != "pending":
            messages.error(request, "Only pending orders can be deleted.")
            return redirect("order-detail", pk=order.pk)

        messages.success(self.request, self.success_message)
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order_items"] = self.object.order_items.all()
        return context


# Add these AJAX views for managing order items
@method_decorator(login_required, name="dispatch")
class OrderItemCreateView(View):
    def post(self, request, order_id):
        try:
            order = get_object_or_404(Order, id=order_id, status="pending")
            product_id = request.POST.get("product_id")
            quantity = request.POST.get("quantity")

            if not product_id or not quantity:
                return JsonResponse(
                    {"success": False, "error": "Product and quantity are required."}
                )

            product = get_object_or_404(Product, id=product_id, is_active=True)
            quantity = Decimal(quantity)

            if quantity <= 0:
                return JsonResponse(
                    {"success": False, "error": "Quantity must be positive."}
                )

            # Check if item already exists in order
            existing_item = OrderItem.objects.filter(
                order=order, product=product
            ).first()
            if existing_item:
                existing_item.quantity += quantity
                existing_item.save()
            else:
                OrderItem.objects.create(
                    order=order, product=product, quantity=quantity
                )

            return JsonResponse(
                {"success": True, "message": "Item added to order successfully."}
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})


@method_decorator(login_required, name="dispatch")
class OrderItemUpdateView(View):
    def post(self, request, order_id, item_id):
        try:
            order = get_object_or_404(Order, id=order_id, status="pending")
            order_item = get_object_or_404(OrderItem, id=item_id, order=order)
            quantity = request.POST.get("quantity")

            if not quantity:
                return JsonResponse(
                    {"success": False, "error": "Quantity is required."}
                )

            quantity = Decimal(quantity)

            if quantity <= 0:
                return JsonResponse(
                    {"success": False, "error": "Quantity must be positive."}
                )

            order_item.quantity = quantity
            order_item.save()

            return JsonResponse(
                {"success": True, "message": "Item updated successfully."}
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})


@method_decorator(login_required, name="dispatch")
class OrderItemDeleteView(View):
    def post(self, request, order_id, item_id):
        try:
            order = get_object_or_404(Order, id=order_id, status="pending")
            order_item = get_object_or_404(OrderItem, id=item_id, order=order)
            order_item.delete()

            return JsonResponse(
                {"success": True, "message": "Item removed from order successfully."}
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})


class OrderConfirmView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            with transaction.atomic():
                order = get_object_or_404(Order, pk=pk)

                if order.status != "pending":
                    messages.error(request, "Only pending orders can be confirmed.")
                    return redirect("order-detail", pk=order.pk)

                # Validate and prepare stock items
                stock_issues = []
                for order_item in order.order_items.all():
                    # Get or create stock item
                    stock_item, created = StockItem.objects.get_or_create(
                        product=order_item.product,
                        warehouse=order.warehouse,
                        defaults={
                            "quantity": 0,
                            "unit_cost": order_item.product.cost_price or Decimal("0"),
                            "reorder_threshold": order_item.product.reorder_threshold
                            or Decimal("0"),
                            "procurement_status": "pending",
                        },
                    )

                    if created:
                        stock_issues.append(
                            f"Created new stock entry for {order_item.product.sku} in {order.warehouse.code} (initial quantity: 0)"
                        )

                    # Check stock availability
                    if stock_item.quantity < order_item.quantity:
                        stock_issues.append(
                            f"Insufficient stock for {order_item.product.sku}. Available: {stock_item.quantity}, Required: {order_item.quantity}"
                        )

                # If there are stock issues, show them and don't confirm
                if stock_issues:
                    for issue in stock_issues:
                        messages.error(request, issue)
                    return redirect("order-detail", pk=order.pk)

                # If all validations pass, update stock and confirm order
                for order_item in order.order_items.all():
                    stock_item = StockItem.objects.get(
                        product=order_item.product, warehouse=order.warehouse
                    )

                    # Create stock transaction - THIS AUTOMATICALLY UPDATES THE STOCK
                    StockTransaction.objects.create(
                        stock_item=stock_item,
                        transaction_type="out",
                        quantity=order_item.quantity,
                        reference=f"Order {order.order_number}",
                        notes=f"Stock deducted for order {order.order_number}",
                        created_by=request.user,
                    )

                    if stock_item.is_low_stock:
                        ReorderAlert.objects.get_or_create(
                            stock_item=stock_item,
                            defaults={
                                "triggered_by": request.user,
                                "status": "active",
                                "notes": f"Low stock triggered by order {order.order_number}",
                            },
                        )

                # Update order status
                order.status = "confirmed"
                order.save()

                messages.success(
                    request, f"Order {order.order_number} confirmed and stock updated."
                )

        except Exception as e:
            messages.error(request, f"Error confirming order: {str(e)}")

        return redirect("order-detail", pk=order.pk)


@require_POST
@login_required
def stock_adjustment_ajax(request):
    try:
        # Try multiple possible field names for stock item ID
        stock_item_id = request.POST.get("stock_item_id") or request.POST.get(
            "stock_item"
        )

        quantity = request.POST.get("quantity")
        reference = request.POST.get("reference", "").strip()
        notes = request.POST.get("notes", "").strip()

        # Validate required fields
        if not stock_item_id:
            return JsonResponse(
                {"success": False, "error": "Stock item is required"}, status=400
            )

        if not quantity:
            return JsonResponse(
                {"success": False, "error": "Quantity is required"}, status=400
            )

        try:
            quantity = Decimal(quantity)
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "error": "Invalid quantity format"}, status=400
            )

        with transaction.atomic():
            # Get and lock the stock item
            stock_item = StockItem.objects.select_for_update().get(pk=stock_item_id)

            # Store old quantity for transaction
            old_quantity = stock_item.quantity

            # Update the stock item quantity directly
            stock_item.quantity = quantity
            stock_item.save()

            # Create the transaction with the DIFFERENCE (not absolute value)
            quantity_difference = quantity - old_quantity

            # Create reference if not provided
            if not reference:
                reference = f"Adjustment-{timezone.now().strftime('%Y%m%d-%H%M%S')}"

            # Create the transaction
            stock_transaction = StockTransaction.objects.create(
                stock_item=stock_item,
                transaction_type="adjustment",
                quantity=quantity_difference,
                reference=reference,
                notes=notes,
                created_by=request.user,
            )

            # Try finance integration but don't fail if it errors
            try:
                if stock_item.unit_cost and quantity_difference != 0:
                    FinanceIntegrationService.create_stock_adjustment_entry(
                        stock_transaction=stock_transaction,
                        adjustment_amount=quantity_difference,
                        unit_cost=stock_item.unit_cost,
                    )
            except Exception as finance_error:
                print(f"Finance integration skipped: {finance_error}")
                # Don't fail the stock adjustment if finance integration fails

            # Return success response
            return JsonResponse(
                {
                    "success": True,
                    "message": "Stock adjusted successfully.",
                    "new_quantity": float(stock_item.quantity),
                    "uom": stock_item.product.unit_of_measure.symbol,
                }
            )

    except StockItem.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Stock item not found."}, status=404
        )
    except Exception as e:
        # Check if it's a finance-related error and handle gracefully
        if "transaction_id" in str(e).lower() or "finance" in str(e).lower():
            return JsonResponse(
                {
                    "success": True,
                    "message": "Stock adjusted successfully (finance integration pending)",
                    "new_quantity": float(stock_item.quantity),
                    "uom": stock_item.product.unit_of_measure.symbol,
                }
            )
        else:
            return JsonResponse(
                {"success": False, "error": f"Server error: {str(e)}"}, status=400
            )


@require_POST
@login_required
def order_create_ajax(request):
    try:
        data = json.loads(request.body)
        items = data.get("items", [])
        warehouse_id = data.get("warehouse")
        notes = data.get("notes", "")

        if not items:
            return JsonResponse(
                {"success": False, "error": "No items provided"}, status=400
            )

        warehouse = get_object_or_404(Warehouse, id=warehouse_id)

        with transaction.atomic():
            order = Order.objects.create(
                warehouse=warehouse,
                created_by=request.user,
                status="pending",
                notes=notes,
            )

            for item in items:
                product = get_object_or_404(Product, id=item["product_id"])
                OrderItem.objects.create(
                    order=order, product=product, quantity=Decimal(item["quantity"])
                )

        return JsonResponse(
            {"success": True, "order_number": order.order_number, "order_id": order.id}
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@method_decorator(login_required, name="dispatch")
class LowStockAPIView(View):
    def get(self, request):
        try:
            low_stock_items = StockItem.objects.filter(
                quantity__lte=F("reorder_threshold")
            ).select_related("product", "warehouse")

            data = {
                "success": True,
                "count": low_stock_items.count(),
                "low_stock_items": [
                    {
                        "id": item.id,
                        "product_sku": item.product.sku,
                        "product_name": item.product.name,
                        "warehouse": item.warehouse.name,
                        "quantity": float(item.quantity),
                        "reorder_threshold": float(item.reorder_threshold),
                        "unit_cost": float(item.unit_cost),
                        "total_value": float(item.total_value),
                        "batch_number": item.batch_number,
                        "location": item.location,
                        "is_expired": item.is_expired,
                        "usage_rate": float(item.usage_rate),
                        "forecast_reorder_date": (
                            item.forecast_reorder_date.strftime("%Y-%m-%d")
                            if item.forecast_reorder_date
                            else None
                        ),
                        "procurement_status": item.procurement_status,
                    }
                    for item in low_stock_items
                ],
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


@method_decorator(login_required, name="dispatch")
class ProcurementUpdateAPIView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            stock_item_id = data.get("stock_item_id")
            new_status = data.get("procurement_status")
            stock_item = StockItem.objects.get(id=stock_item_id)

            if new_status in ["none", "pending", "ordered", "delivered"]:
                stock_item.procurement_status = new_status
                stock_item.save()

                # Create or update reorder alert
                if new_status in ["pending", "ordered"]:
                    ReorderAlert.objects.get_or_create(
                        stock_item=stock_item,
                        defaults={"triggered_by": request.user, "status": "active"},
                    )
                elif new_status == "delivered":
                    ReorderAlert.objects.filter(
                        stock_item=stock_item, status="active"
                    ).update(
                        status="resolved", notes=f"Resolved on {timezone.now().date()}"
                    )

                return JsonResponse(
                    {"success": True, "message": "Procurement status updated"}
                )
            else:
                return JsonResponse(
                    {"success": False, "error": "Invalid status"}, status=400
                )
        except StockItem.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Stock item not found"}, status=404
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


@method_decorator(login_required, name="dispatch")
class DashboardDataAPIView(View):
    def get(self, request):
        try:
            # Fetch summary statistics
            stock_items = StockItem.objects.select_related("product", "warehouse")
            total_items = stock_items.count()
            total_value = sum(float(item.total_value) for item in stock_items)
            low_stock_count = stock_items.filter(
                quantity__lte=F("reorder_threshold")
            ).count()
            out_of_stock_count = stock_items.filter(quantity__lte=0).count()
            reorder_alert_count = ReorderAlert.objects.filter(status="active").count()

            # Stock status for chart
            stock_status = stock_items.aggregate(
                in_stock=Count(
                    "id",
                    filter=~Q(quantity__lte=F("reorder_threshold"))
                    & ~Q(quantity__lte=0),
                ),
                low_stock=Count(
                    "id",
                    filter=Q(quantity__lte=F("reorder_threshold"))
                    & ~Q(quantity__lte=0),
                ),
                out_of_stock=Count("id", filter=Q(quantity__lte=0)),
            )

            # Recent stock items (limited to 10 for display)
            recent_items = stock_items.order_by("product__sku", "batch_number")[:10]

            data = {
                "success": True,
                "total_items": total_items,
                "total_value": float(total_value),
                "low_stock_count": low_stock_count,
                "out_of_stock_count": out_of_stock_count,
                "reorder_alert_count": reorder_alert_count,
                "stock_status": stock_status,
                "stock_items": [
                    {
                        "id": item.id,
                        "product_sku": item.product.sku,
                        "product_name": item.product.name,
                        "batch_number": item.batch_number or "-",
                        "warehouse_code": item.warehouse.code,
                        "quantity": float(item.quantity),
                        "unit_of_measure": item.product.unit_of_measure.symbol,
                        "total_value": float(item.total_value),
                        "is_low_stock": item.is_low_stock,
                        "is_out_of_stock": item.quantity <= 0,
                    }
                    for item in recent_items
                ],
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class PrintLabelView(LoginRequiredMixin, DetailView):
    model = StockItem

    def get(self, request, *args, **kwargs):
        item = self.get_object()
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{item.product.sku}_label.pdf"'
        )
        p = canvas.Canvas(response)
        p.drawString(100, 800, f"SKU: {item.product.sku}")
        p.drawString(100, 780, f"Name: {item.product.name}")
        p.drawString(100, 760, f"Batch: {item.batch_number or '-'}")
        p.drawString(100, 740, f"Expiry: {item.expiry_date or '-'}")
        p.save()
        return response


class StockCountCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            with transaction.atomic():
                stock_item = StockItem.objects.select_for_update().get(id=pk)
                counted = Decimal(request.POST["counted_quantity"])
                notes = request.POST.get("notes", "")
                diff = counted - stock_item.quantity
                if diff != 0:
                    StockTransaction.objects.create(
                        stock_item=stock_item,
                        transaction_type="adjustment",
                        quantity=diff,
                        reference="Stock Count Adjustment",
                        notes=notes,
                        created_by=request.user,
                    )
                return JsonResponse(
                    {"success": True, "message": "Stock count submitted."}
                )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)


class QualityCheckCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            stock_item = StockItem.objects.get(id=pk)
            status = request.POST["status"]
            notes = request.POST["notes"]
            # Assuming a QualityCheck model exists; otherwise, log as transaction
            StockTransaction.objects.create(
                stock_item=stock_item,
                transaction_type="quality",
                quantity=0,  # no quantity change
                reference=f"Quality Check: {status.upper()}",
                notes=notes,
                created_by=request.user,
            )
            return JsonResponse(
                {"success": True, "message": "Quality check submitted."}
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)


# views.py - Update the LowStockToRequisitionView

@method_decorator(ensure_csrf_cookie, name='dispatch')
class LowStockToRequisitionView(LoginRequiredMixin, View):
    """Convert low stock items to purchase requisition"""
    
    def post(self, request):
        try:
            logger.info(f"LowStockToRequisitionView called by user: {request.user}")
            
            # Parse JSON data
            try:
                data = json.loads(request.body.decode('utf-8'))
                logger.info(f"Received data: {data}")
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"JSON decode error: {str(e)}")
                return JsonResponse({
                    'success': False, 
                    'error': f'Invalid JSON data: {str(e)}'
                }, status=400)
            
            stock_item_ids = data.get('stock_item_ids', [])
            department = data.get('department', 'Inventory')
            
            logger.info(f"Processing {len(stock_item_ids)} stock items for department: {department}")
            
            if not stock_item_ids:
                logger.warning("No stock item IDs provided")
                return JsonResponse({
                    'success': False, 
                    'error': 'No stock items selected'
                }, status=400)
            
            # Get low stock items with proper filtering
            from django.db.models import F
            low_stock_items = StockItem.objects.filter(
                id__in=stock_item_ids,
                quantity__lte=F('product__reorder_threshold'),
                quantity__gt=0
            ).select_related('product', 'warehouse', 'product__unit_of_measure')
            
            logger.info(f"Found {low_stock_items.count()} low stock items matching criteria")
            
            if not low_stock_items:
                logger.warning("No valid low stock items found")
                return JsonResponse({
                    'success': False, 
                    'error': 'No valid low stock items found'
                }, status=400)
            
            # Log detailed information about each item
            for item in low_stock_items:
                logger.info(f"Processing item: {item.product.sku}, "
                          f"Qty: {item.quantity}, "
                          f"Threshold: {item.product.reorder_threshold}, "
                          f"Unit Cost: {item.unit_cost}, "
                          f"Product Cost: {item.product.cost_price}")
            
            # Create requisition using the procurement service
            try:
                requisition = ProcurementIntegrationService.create_requisition_from_low_stock(
                    low_stock_items=low_stock_items,
                    requested_by=request.user,
                    department=department
                )
                logger.info(f"Successfully created requisition: {requisition.requisition_number}")
                
                # Verify items were created
                item_count = requisition.items.count()
                total_cost = requisition.total_estimated_cost
                logger.info(f"Requisition has {item_count} items with total cost: {total_cost}")
                
            except Exception as service_error:
                logger.error(f"Procurement service error: {str(service_error)}")
                logger.error(traceback.format_exc())
                return JsonResponse({
                    'success': False, 
                    'error': f'Procurement service error: {str(service_error)}'
                }, status=500)
            
            return JsonResponse({
                'success': True,
                'message': f'Requisition {requisition.requisition_number} created successfully',
                'requisition_id': requisition.id,
                'requisition_number': requisition.requisition_number,
                'items_count': requisition.items.count(),
                'total_cost': float(requisition.total_estimated_cost),
                'redirect_url': reverse('requisition-detail', kwargs={'pk': requisition.id})
            })
            
        except Exception as e:
            logger.error(f"Unexpected error in LowStockToRequisitionView: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({
                'success': False, 
                'error': f'Unexpected server error: {str(e)}'
            }, status=500)

@method_decorator(ensure_csrf_cookie, name='dispatch')
class AutoReorderView(LoginRequiredMixin, View):
    """Automatically create requisitions for all active low stock alerts"""
    
    def post(self, request):
        try:
            logger.info(f"AutoReorderView called by user: {request.user}")
            
            # Get all low stock items
            from django.db.models import F
            low_stock_items = StockItem.objects.filter(
                quantity__lte=F('product__reorder_threshold'),
                quantity__gt=0
            ).select_related('product', 'warehouse')
            
            logger.info(f"Found {low_stock_items.count()} total low stock items")
            
            if not low_stock_items:
                logger.info("No low stock items found for auto-reorder")
                return JsonResponse({
                    'success': False, 
                    'error': 'No low stock items found'
                })
            
            # Log the items being processed
            for item in low_stock_items:
                logger.info(f"Auto-reorder item: {item.product.sku}, Qty: {item.quantity}, Threshold: {item.product.reorder_threshold}")
            
            # Create requisition
            try:
                requisition = ProcurementIntegrationService.create_requisition_from_low_stock(
                    low_stock_items=low_stock_items,
                    requested_by=request.user,
                    department='Inventory'
                )
                logger.info(f"Successfully created auto-reorder requisition: {requisition.requisition_number}")
                
            except Exception as service_error:
                logger.error(f"Auto-reorder procurement service error: {str(service_error)}")
                logger.error(traceback.format_exc())
                return JsonResponse({
                    'success': False, 
                    'error': f'Auto-reorder service error: {str(service_error)}'
                }, status=500)
            
            return JsonResponse({
                'success': True,
                'message': f'Auto-reorder completed. Created requisition {requisition.requisition_number}',
                'requisition_id': requisition.id,
                'requisition_number': requisition.requisition_number,
                'items_processed': low_stock_items.count(),
                'total_cost': float(requisition.total_estimated_cost)
            })
            
        except Exception as e:
            logger.error(f"Unexpected error in AutoReorderView: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({
                'success': False, 
                'error': f'Auto-reorder failed: {str(e)}'
            }, status=500)
            
@method_decorator(login_required, name='dispatch')
class LowStockAnalysisView(View):
    """Get low stock analysis data for reporting"""
    
    def get(self, request):
        try:
            analysis = ProcurementIntegrationService.get_low_stock_analysis()
            
            return JsonResponse({
                'success': True,
                'analysis': analysis
            })
            
        except Exception as e:
            logger.error(f'Error getting low stock analysis: {str(e)}')
            return JsonResponse({
                'success': False, 
                'error': str(e)
            }, status=500)

@method_decorator(login_required, name='dispatch')
class ProcurementStatusView(ListView):
    """View to show procurement status for inventory items"""
    
    template_name = "inventory/procurement_status.html"
    context_object_name = "stock_items"
    paginate_by = 20
    
    def get_queryset(self):
        queryset = StockItem.objects.select_related(
            "product", "warehouse"
        ).prefetch_related("reorder_alerts")
        
        # Filter by procurement status
        procurement_status = self.request.GET.get("procurement_status")
        if procurement_status:
            queryset = queryset.filter(procurement_status=procurement_status)
        
        # Filter by warehouse
        warehouse = self.request.GET.get("warehouse")
        if warehouse:
            queryset = queryset.filter(warehouse_id=warehouse)
        
        # Filter by low stock
        low_stock_only = self.request.GET.get("low_stock_only")
        if low_stock_only:
            queryset = queryset.filter(
                quantity__lte=models.F('product__reorder_threshold')
            )
        
        return queryset.order_by("product__sku")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["warehouses"] = Warehouse.objects.filter(is_active=True)
        context["procurement_statuses"] = [
            ("pending", "Pending"),
            ("ordered", "Ordered"),
            ("received", "Received"),
        ]
        
        # Add summary statistics
        queryset = self.get_queryset()
        context["total_items"] = queryset.count()
        context["low_stock_count"] = queryset.filter(
            quantity__lte=models.F('product__reorder_threshold')
        ).count()
        context["ordered_count"] = queryset.filter(procurement_status='ordered').count()
        context["received_count"] = queryset.filter(procurement_status='received').count()
        
        return context

class InventorySalesIntegrationMixin:
    """Mixin for inventory-sales integration"""

    def check_stock_availability(self, product, quantity, warehouse=None):
        """Check if product is available in specified quantity"""
        if warehouse:
            stock_items = StockItem.objects.filter(
                product=product, warehouse=warehouse, quantity__gte=quantity
            )
        else:
            stock_items = StockItem.objects.filter(
                product=product, quantity__gte=quantity
            )

        return stock_items.first()

    def get_available_stock_info(self, product):
        """Get comprehensive stock information for a product"""
        stock_items = StockItem.objects.filter(product=product, quantity__gt=0)

        total_available = stock_items.aggregate(total=Sum("quantity"))["total"] or 0
        warehouses_with_stock = []

        for item in stock_items:
            warehouses_with_stock.append(
                {
                    "warehouse": item.warehouse,
                    "quantity": item.quantity,
                    "stock_item": item,
                }
            )

        return {
            "total_available": total_available,
            "warehouses_with_stock": warehouses_with_stock,
            "is_available": total_available > 0,
        }


# Add to existing StockItemListView
def stock_check_ajax(request):
    """AJAX endpoint for sales to check stock availability"""
    product_id = request.GET.get("product_id")
    quantity = Decimal(request.GET.get("quantity", 0))

    if not product_id or quantity <= 0:
        return JsonResponse({"error": "Invalid parameters"})

    try:
        product = Product.objects.get(id=product_id)
        available_stock = (
            StockItem.objects.filter(product=product, quantity__gte=quantity)
            .select_related("warehouse")
            .first()
        )

        if available_stock:
            return JsonResponse(
                {
                    "available": True,
                    "warehouse": available_stock.warehouse.code,
                    "warehouse_name": available_stock.warehouse.name,
                    "available_quantity": float(available_stock.quantity),
                    "stock_item_id": available_stock.id,
                }
            )
        else:
            total_stock = (
                StockItem.objects.filter(product=product).aggregate(
                    total=Sum("quantity")
                )["total"]
                or 0
            )

            return JsonResponse(
                {
                    "available": False,
                    "total_available": float(total_stock),
                    "message": f"Insufficient stock. Available: {total_stock}",
                }
            )

    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"})


# Add inventory permissions check
def has_inventory_permission(user):
    """Check if user has inventory department permissions"""
    return (
        user.groups.filter(name__in=["Inventory Manager", "Inventory Staff"]).exists()
        or user.is_superuser
    )


@require_http_methods(["GET"])
def stock_availability_api(request):
    """API endpoint for checking stock availability"""
    product_id = request.GET.get("product_id")
    quantity = request.GET.get("quantity", "0")
    warehouse_id = request.GET.get("warehouse_id")

    try:
        quantity = Decimal(quantity)
        if quantity <= 0:
            return JsonResponse(
                {"error": "Quantity must be greater than 0"}, status=400
            )

        product = Product.objects.get(id=product_id, is_active=True)

        # Build query based on parameters
        stock_query = StockItem.objects.filter(product=product, quantity__gt=0)

        if warehouse_id:
            stock_query = stock_query.filter(
                warehouse_id=warehouse_id, quantity__gte=quantity
            )

        available_stock = (
            stock_query.select_related("warehouse").order_by("-quantity").first()
        )

        if available_stock:
            return JsonResponse(
                {
                    "available": True,
                    "product_id": product.id,
                    "product_sku": product.sku,
                    "product_name": product.name,
                    "warehouse_id": available_stock.warehouse.id,
                    "warehouse_code": available_stock.warehouse.code,
                    "warehouse_name": available_stock.warehouse.name,
                    "available_quantity": float(available_stock.quantity),
                    "stock_item_id": available_stock.id,
                    "unit_of_measure": (
                        product.unit_of_measure.symbol
                        if product.unit_of_measure
                        else "unit"
                    ),
                }
            )
        else:
            # Get total available stock across all warehouses
            total_stock = (
                StockItem.objects.filter(product=product).aggregate(
                    total=Sum("quantity")
                )["total"]
                or 0
            )

            # Get warehouses with any stock
            warehouses_with_stock = (
                StockItem.objects.filter(product=product, quantity__gt=0)
                .select_related("warehouse")
                .values(
                    "warehouse_id", "warehouse__code", "warehouse__name", "quantity"
                )
            )

            return JsonResponse(
                {
                    "available": False,
                    "product_id": product.id,
                    "product_sku": product.sku,
                    "product_name": product.name,
                    "total_available_quantity": float(total_stock),
                    "warehouses_with_stock": list(warehouses_with_stock),
                    "message": f"Insufficient stock. Required: {quantity}, Available: {total_stock}",
                }
            )

    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)
    except ValueError:
        return JsonResponse({"error": "Invalid quantity format"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)


@require_http_methods(["POST"])
@csrf_exempt
def bulk_stock_check_api(request):
    """API endpoint for checking stock availability for multiple products"""
    try:
        data = json.loads(request.body)
        products_data = data.get("products", [])

        if not products_data:
            return JsonResponse({"error": "No products provided"}, status=400)

        results = []
        all_available = True

        for product_data in products_data:
            product_id = product_data.get("product_id")
            quantity = Decimal(product_data.get("quantity", "0"))

            if quantity <= 0:
                results.append(
                    {
                        "product_id": product_id,
                        "available": False,
                        "error": "Invalid quantity",
                    }
                )
                all_available = False
                continue

            try:
                product = Product.objects.get(id=product_id, is_active=True)

                # Check available stock
                available_stock = (
                    StockItem.objects.filter(product=product, quantity__gte=quantity)
                    .select_related("warehouse")
                    .first()
                )

                if available_stock:
                    results.append(
                        {
                            "product_id": product.id,
                            "product_sku": product.sku,
                            "product_name": product.name,
                            "available": True,
                            "warehouse_id": available_stock.warehouse.id,
                            "warehouse_code": available_stock.warehouse.code,
                            "available_quantity": float(available_stock.quantity),
                            "stock_item_id": available_stock.id,
                        }
                    )
                else:
                    total_stock = (
                        StockItem.objects.filter(product=product).aggregate(
                            total=Sum("quantity")
                        )["total"]
                        or 0
                    )

                    results.append(
                        {
                            "product_id": product.id,
                            "product_sku": product.sku,
                            "product_name": product.name,
                            "available": False,
                            "total_available_quantity": float(total_stock),
                            "required_quantity": float(quantity),
                            "message": f"Insufficient stock. Required: {quantity}, Available: {total_stock}",
                        }
                    )
                    all_available = False

            except Product.DoesNotExist:
                results.append(
                    {
                        "product_id": product_id,
                        "available": False,
                        "error": "Product not found",
                    }
                )
                all_available = False
            except Exception as e:
                results.append(
                    {
                        "product_id": product_id,
                        "available": False,
                        "error": f"Error checking stock: {str(e)}",
                    }
                )
                all_available = False

        return JsonResponse({"all_available": all_available, "results": results})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON data"}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)


@require_http_methods(["GET"])
def get_stock_items_ajax(request):
    """AJAX endpoint to get stock items for a product"""
    product_id = request.GET.get("product_id")

    if not product_id:
        return JsonResponse({"error": "Product ID required"}, status=400)

    try:
        stock_items = (
            StockItem.objects.filter(product_id=product_id, quantity__gt=0)
            .select_related("warehouse", "product", "product__unit_of_measure")
            .only(
                "id",
                "warehouse__code",
                "warehouse__name",
                "quantity",
                "batch_number",
                "location",
                "product__sku",
                "product__name",
                "product__unit_of_measure__symbol",
                "product__product_type",
            )
        )

        results = []
        for item in stock_items:
            results.append(
                {
                    "id": item.id,
                    "text": (
                        f"{item.warehouse.code} - {item.quantity} "
                        f"{item.product.unit_of_measure.symbol if item.product.unit_of_measure else 'unit'}"
                    ),
                    "warehouse_id": item.warehouse.id,
                    "warehouse_code": item.warehouse.code,
                    "warehouse_name": item.warehouse.name,
                    "quantity": float(item.quantity),
                    "unit_cost": float(item.product.cost_price),
                    "batch_number": item.batch_number or "",
                    "location": item.location or "",
                    "product_type": item.product.product_type,
                    "product_type_display": item.product.get_product_type_display(),
                }
            )

        return JsonResponse({"results": results})

    except Exception as e:
        return JsonResponse(
            {"error": f"Error fetching stock items: {str(e)}"}, status=500
        )

class CheckInventoryView(LoginRequiredMixin, View):
    def get(self, request, pk):
        """Display inventory check page"""
        inquiry = get_object_or_404(SalesInquiry, pk=pk, status='submitted')
        
        context = {
            'inquiry': inquiry,
            'items': inquiry.items.select_related('product'),
        }
        
        # Pre-check stock for display
        for item in context['items']:
            item.available_stock = StockItem.objects.filter(
                product=item.product
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            item.suggested_stock = StockItem.objects.filter(
                product=item.product,
                quantity__gte=item.quantity
            ).select_related('warehouse').first()
        
        return render(request, 'inventory/check_inventory.html', context)
    
    def post(self, request, pk):
        """Process inventory check response"""
        inquiry = get_object_or_404(SalesInquiry, pk=pk, status='submitted')
        
        # Check if user has inventory permissions
        if not self._has_inventory_permission(request.user):
            messages.error(request, 'You do not have permission to check inventory.')
            return redirect('inventory-inquiry-list')
        
        try:
            with transaction.atomic():
                all_available = True
                inventory_response = []
                manual_override = request.POST.get('manual_override') == 'true'
                
                for item in inquiry.items.all():
                    product_id = str(item.product.id)
                    
                    if manual_override:
                        # Allow manual override of availability
                        is_available = request.POST.get(f'available_{product_id}') == 'true'
                        if is_available:
                            # Find suitable warehouse
                            available_stock = StockItem.objects.filter(
                                product=item.product,
                                quantity__gte=item.quantity
                            ).select_related('warehouse').first()
                            
                            if available_stock:
                                item.is_available = True
                                item.available_quantity = available_stock.quantity
                                item.suggested_warehouse = available_stock.warehouse
                                item.suggested_stock_item = available_stock
                                inventory_response.append(
                                    f"✓ {item.product.sku}: Available ({available_stock.quantity} in {available_stock.warehouse.code})"
                                )
                            else:
                                # Even with manual override, we need actual stock
                                item.is_available = False
                                item.available_quantity = 0
                                all_available = False
                                inventory_response.append(
                                    f"✗ {item.product.sku}: No stock available despite manual override"
                                )
                        else:
                            item.is_available = False
                            total_stock = StockItem.objects.filter(
                                product=item.product
                            ).aggregate(total=Sum('quantity'))['total'] or 0
                            item.available_quantity = total_stock
                            inventory_response.append(
                                f"✗ {item.product.sku}: Manually marked as unavailable"
                            )
                    else:
                        # Automatic stock check (original logic)
                        available_stock = StockItem.objects.filter(
                            product=item.product,
                            quantity__gte=item.quantity
                        ).select_related('warehouse').first()
                        
                        if available_stock:
                            item.is_available = True
                            item.available_quantity = available_stock.quantity
                            item.suggested_warehouse = available_stock.warehouse
                            item.suggested_stock_item = available_stock
                            inventory_response.append(
                                f"✓ {item.product.sku}: Available ({available_stock.quantity} in {available_stock.warehouse.code})"
                            )
                        else:
                            total_stock = StockItem.objects.filter(
                                product=item.product
                            ).aggregate(total=Sum('quantity'))['total'] or 0
                            
                            item.is_available = False
                            item.available_quantity = total_stock
                            all_available = False
                            
                            if total_stock > 0:
                                inventory_response.append(
                                    f"⚠ {item.product.sku}: Partial stock (Available: {total_stock}, Required: {item.quantity})"
                                )
                            else:
                                inventory_response.append(
                                    f"✗ {item.product.sku}: Out of stock"
                                )
                    
                    item.save()
                
                inquiry.inventory_checked_by = request.user
                inquiry.inventory_responded_at = timezone.now()
                inquiry.inventory_response = "\n".join(inventory_response)
                
                if all_available or (manual_override and all_available):
                    inquiry.status = 'approved'
                    message = 'All products available. Inquiry approved!'
                else:
                    inquiry.status = 'rejected'
                    message = 'Some products unavailable. Inquiry rejected.'
                
                inquiry.save()
                
                # Create notification for sales team
                self._create_notification(inquiry, request.user)
                
                messages.success(request, message)
                return redirect('inventory-inquiry-detail', pk=inquiry.pk)
                
        except Exception as e:
            messages.error(request, f'Error checking inventory: {str(e)}')
            return redirect('inventory-inquiry-detail', pk=inquiry.pk)
    
    def _has_inventory_permission(self, user):
        """Check if user has inventory department permissions"""
        return (
            user.groups.filter(name__in=['Inventory Manager', 'Inventory Clerk', 'Inventory Staff']).exists()
            or user.is_superuser
        )
    
    def _create_notification(self, inquiry, checked_by):
        """Create notification for sales team about inventory check result"""
        # You can implement your notification system here
        # This could be Django messages, emails, or a custom notification model
        pass

class InventoryInquiryListView(LoginRequiredMixin, ListView):
    """View for inventory clerks to see submitted inquiries"""
    model = SalesInquiry
    template_name = 'inventory/inquiry_list.html'
    context_object_name = 'inquiries'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = SalesInquiry.objects.filter(
            status='submitted'
        ).select_related(
            'customer', 'requested_by'
        ).prefetch_related('items')
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(inquiry_number__icontains=search) |
                Q(customer__name__icontains=search)
            )
        
        return queryset.order_by('-inquiry_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pending_count'] = SalesInquiry.objects.filter(status='submitted').count()
        return context

class InventoryInquiryDetailView(LoginRequiredMixin, DetailView):
    """Detailed view for inventory clerks to check stock"""
    model = SalesInquiry
    template_name = 'inventory/inquiry_detail.html'
    context_object_name = 'inquiry'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inquiry = self.object
        
        context['items'] = inquiry.items.select_related(
            'product', 'suggested_warehouse', 'suggested_stock_item'
        )
        
        # Add stock information for each product
        for item in context['items']:
            item.available_stock = StockItem.objects.filter(
                product=item.product
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            # Get warehouses with available stock
            item.warehouse_stock = StockItem.objects.filter(
                product=item.product,
                quantity__gt=0
            ).select_related('warehouse')
        
        return context

class ApproveInquiryView(LoginRequiredMixin, View):
    """Quick approve action for inventory clerks"""
    def post(self, request, pk):
        inquiry = get_object_or_404(SalesInquiry, pk=pk, status='submitted')
        
        if not self._has_inventory_permission(request.user):
            messages.error(request, 'You do not have permission to approve inquiries.')
            return redirect('inventory-inquiry-list')
        
        try:
            with transaction.atomic():
                # Verify all items are available
                for item in inquiry.items.all():
                    available_stock = StockItem.objects.filter(
                        product=item.product,
                        quantity__gte=item.quantity
                    ).first()
                    
                    if not available_stock:
                        messages.error(request, f'Cannot approve: {item.product.sku} has insufficient stock.')
                        return redirect('inventory-inquiry-detail', pk=inquiry.pk)
                    
                    # Update item with stock information
                    item.is_available = True
                    item.available_quantity = available_stock.quantity
                    item.suggested_warehouse = available_stock.warehouse
                    item.suggested_stock_item = available_stock
                    item.save()
                
                inquiry.status = 'approved'
                inquiry.inventory_checked_by = request.user
                inquiry.inventory_responded_at = timezone.now()
                inquiry.inventory_response = "All items approved - sufficient stock available"
                inquiry.save()
                
                messages.success(request, f'Inquiry {inquiry.inquiry_number} approved!')
                return redirect('inventory-inquiry-list')
                
        except Exception as e:
            messages.error(request, f'Error approving inquiry: {str(e)}')
            return redirect('inventory-inquiry-detail', pk=inquiry.pk)
    
    def _has_inventory_permission(self, user):
        return user.groups.filter(name__in=['Inventory Manager', 'Inventory Clerk', 'Administrator']).exists()

class RejectInquiryView(LoginRequiredMixin, View):
    """Quick reject action for inventory clerks"""
    def post(self, request, pk):
        inquiry = get_object_or_404(SalesInquiry, pk=pk, status='submitted')
        
        if not self._has_inventory_permission(request.user):
            messages.error(request, 'You do not have permission to reject inquiries.')
            return redirect('inventory-inquiry-list')
        
        reason = request.POST.get('reason', 'Insufficient stock')
        
        try:
            with transaction.atomic():
                # Mark all items as unavailable
                for item in inquiry.items.all():
                    total_stock = StockItem.objects.filter(
                        product=item.product
                    ).aggregate(total=Sum('quantity'))['total'] or 0
                    
                    item.is_available = False
                    item.available_quantity = total_stock
                    item.save()
                
                inquiry.status = 'rejected'
                inquiry.inventory_checked_by = request.user
                inquiry.inventory_responded_at = timezone.now()
                inquiry.inventory_response = f"Rejected: {reason}"
                inquiry.save()
                
                messages.warning(request, f'Inquiry {inquiry.inquiry_number} rejected.')
                return redirect('inventory-inquiry-list')
                
        except Exception as e:
            messages.error(request, f'Error rejecting inquiry: {str(e)}')
            return redirect('inventory-inquiry-detail', pk=inquiry.pk)
    
    def _has_inventory_permission(self, user):
        return user.groups.filter(name__in=['Inventory Manager', 'Inventory Clerk', 'Administrator']).exists()