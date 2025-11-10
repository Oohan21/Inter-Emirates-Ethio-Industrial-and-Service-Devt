from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404, render
from datetime import timedelta
import uuid
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import get_user_model
from django.views.generic import ListView, DetailView, TemplateView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, F, Sum, Count, FloatField, Value, Case, When, DecimalField
from decimal import Decimal
from django.contrib.messages.views import SuccessMessageMixin
from django.utils import timezone
from django.db import transaction as db_transaction
from .services.finance_integration import FinanceIntegrationService
from .models import Order, OrderItem, Warehouse, StockItem, StockTransaction, ReorderAlert
from apps.products.models import Product, Category
from .forms import StockAdjustmentForm, StockItemForm, WarehouseForm
from django.views import View
from django import forms
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
import json
import csv
from django.urls import reverse_lazy
from django.db.models.functions import Coalesce
from reportlab.pdfgen import canvas

User = get_user_model()

class StockItemCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = StockItem
    form_class = StockItemForm
    template_name = 'inventory/stock_item_form.html'
    success_url = reverse_lazy('stock-item-list')
    success_message = "Stock item added successfully."

    def form_valid(self, form):
        response = super().form_valid(form)
        # Create initial transaction
        StockTransaction.objects.create(
            stock_item=self.object,
            transaction_type='adjustment',
            quantity=self.object.quantity,
            reference='Initial Stock',
            notes='Initial stock addition',
            created_by=self.request.user
        )
        messages.success(self.request, self.success_message)
        return response

class WarehouseListView(LoginRequiredMixin, ListView):
    model = Warehouse
    template_name = 'inventory/warehouse_list.html'
    context_object_name = 'warehouses'
    
    def get_queryset(self):
        return Warehouse.objects.filter(is_active=True).prefetch_related(
            'stock_items',
            'stock_items__product',
            'manager'
        ).order_by('code')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        warehouses = context['warehouses']
        total_warehouses = warehouses.count()
        active_warehouses = total_warehouses
        
        # Calculate low stock and out of stock counts
        total_low_stock = 0
        total_out_of_stock = 0
        
        for warehouse in warehouses:
            total_low_stock += warehouse.low_stock_count
            total_out_of_stock += warehouse.out_of_stock_count
        
        context.update({
            'total_warehouses': total_warehouses,
            'active_warehouses': active_warehouses,
            'total_low_stock': total_low_stock,
            'total_out_of_stock': total_out_of_stock,
        })
        
        return context

class WarehouseCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'inventory/warehouse_form.html'
    success_url = reverse_lazy('warehouse-list')
    success_message = "Warehouse created successfully."

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

class WarehouseUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'inventory/warehouse_form.html'
    success_url = reverse_lazy('warehouse-list')
    success_message = "Warehouse updated successfully."

class WarehouseDeleteView(LoginRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Warehouse
    template_name = 'inventory/warehouse_confirm_delete.html'
    success_url = reverse_lazy('warehouse-list')
    success_message = "Warehouse deleted successfully."

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        return super().delete(request, *args, **kwargs)

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

class StockAdjustmentCreateView(LoginRequiredMixin, CreateView):
    model = StockTransaction
    form_class = StockAdjustmentForm
    template_name = 'inventory/stock_adjustment.html'
    success_url = reverse_lazy('stock-item-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial'] = {
            'created_by': self.request.user,
            'transaction_type': 'adjustment'
        }
        return kwargs
        
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.transaction_type = 'adjustment'
        
        stock_item = form.cleaned_data['stock_item']
        new_quantity = form.cleaned_data['quantity']
        stock_item.quantity = new_quantity
        stock_item.save()
        
        response = super().form_valid(form)
        
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        return response

    def form_invalid(self, form):
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        return super().form_invalid(form)

class StockItemDetailView(LoginRequiredMixin, DetailView):
    model = StockItem
    template_name = 'inventory/stock_item_detail.html'
    context_object_name = 'stock_item'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['warehouses'] = Warehouse.objects.filter(is_active=True)
        ctx['recent_transactions'] = self.object.transactions.order_by('-created_at')[:10]
        return ctx

    def get_queryset(self):
        return StockItem.objects.select_related('product', 'warehouse').prefetch_related('transactions')

class StockTransactionListView(LoginRequiredMixin, ListView):
    model = StockTransaction
    template_name = 'inventory/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = StockTransaction.objects.select_related(
            'stock_item__product', 
            'stock_item__warehouse',
            'created_by'
        )
        
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
        
        return queryset.order_by('-created_at')
    
    def post(self, request):
        try:
            with transaction.atomic():
                stock_item = StockItem.objects.select_for_update().get(id=request.POST['stock_item'])
                new_qty = Decimal(request.POST['quantity'])
                reference = request.POST.get('reference', '').strip()
                notes = request.POST.get('notes', '').strip()

                # create transaction
                tx = StockTransaction.objects.create(
                    stock_item=stock_item,
                    transaction_type='adjustment',
                    quantity=new_qty,              
                    reference=reference or 'Manual adjustment',
                    notes=notes,
                    created_by=request.user
                )
                stock_item.refresh_from_db()

                return JsonResponse({
                    'success': True,
                    'message': 'Stock adjusted.',
                    'new_quantity': float(stock_item.quantity),
                    'uom': stock_item.product.unit_of_measure.symbol
                })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

class StockTransactionCreateView(LoginRequiredMixin, CreateView):
    model = StockTransaction
    template_name = 'inventory/stock_transaction.html'
    fields = ['stock_item', 'quantity', 'reference', 'notes']
    success_url = reverse_lazy('stock-item-list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return form

    def post(self, request, *args, **kwargs):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return self.handle_ajax_request(request)
        return super().post(request, *args, **kwargs)

    def handle_ajax_request(self, request):
        try:
            with transaction.atomic():
                stock_item_id = request.POST.get('stock_item')
                quantity = Decimal(request.POST.get('quantity'))
                destination_warehouse_id = request.POST.get('destination_warehouse')
                reference = request.POST.get('reference', '').strip()
                notes = request.POST.get('notes', '').strip()

                if not all([stock_item_id, quantity, destination_warehouse_id]):
                    return JsonResponse({
                        'success': False, 
                        'error': 'Missing required fields'
                    }, status=400)

                source_stock = StockItem.objects.select_for_update().get(id=stock_item_id)
                
                if quantity > source_stock.quantity:
                    return JsonResponse({
                        'success': False, 
                        'error': f'Transfer quantity ({quantity}) exceeds available stock ({source_stock.quantity})'
                    }, status=400)

                # Get destination warehouse
                try:
                    destination_warehouse = Warehouse.objects.get(id=destination_warehouse_id, is_active=True)
                except Warehouse.DoesNotExist:
                    return JsonResponse({
                        'success': False, 
                        'error': 'Invalid destination warehouse'
                    }, status=400)

                destination_stock, created = StockItem.objects.get_or_create(
                    product=source_stock.product,
                    warehouse=destination_warehouse,
                    batch_number=source_stock.batch_number,
                    defaults={
                        'quantity': 0,
                        'unit_cost': source_stock.unit_cost,
                        'reorder_threshold': source_stock.reorder_threshold,
                        'location': source_stock.location,
                        'expiry_date': source_stock.expiry_date,
                        'manufactured_date': source_stock.manufactured_date,
                        'notes': source_stock.notes,
                    }
                )

                source_stock.quantity -= quantity
                destination_stock.quantity += quantity
                source_stock.save()
                destination_stock.save()

                # Create transfer transaction for source (out)
                StockTransaction.objects.create(
                    stock_item=source_stock,
                    transaction_type='out',
                    quantity=quantity,
                    reference=reference or f"Transfer to {destination_warehouse.code}",
                    notes=f"Transferred to {destination_warehouse.name}. {notes}",
                    created_by=self.request.user
                )

                # Create transfer transaction for destination (in)
                StockTransaction.objects.create(
                    stock_item=destination_stock,
                    transaction_type='in',
                    quantity=quantity,
                    reference=reference or f"Transfer from {source_stock.warehouse.code}",
                    notes=f"Transferred from {source_stock.warehouse.name}. {notes}",
                    created_by=self.request.user
                )

                # Check for low stock alert
                if source_stock.is_low_stock:
                    ReorderAlert.objects.get_or_create(
                        stock_item=source_stock,
                        defaults={
                            'triggered_by': self.request.user,
                            'status': 'active',
                            'notes': f"Low stock after transfer to {destination_warehouse.name}"
                        }
                    )

                return JsonResponse({
                    'success': True,
                    'message': f'Stock transferred successfully to {destination_warehouse.name}',
                    'new_quantity': float(source_stock.quantity)
                })

        except StockItem.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': 'Source stock item not found'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'error': f'Transfer failed: {str(e)}'
            }, status=500)

    def form_valid(self, form):
        form.instance.transaction_type = 'transfer'
        form.instance.created_by = self.request.user
        return super().form_valid(form)

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
        context['warehouses'] = Warehouse.objects.filter(is_active=True)

        # Summary stats
        context['total_low_stock'] = items.count()
        context['total_deficit'] = sum(
            float(item.stock_deficit) for item in items
        )
        context['total_value_at_risk'] = sum(
            float(item.total_value) for item in items
        )

        return context

class OrderCreateView(LoginRequiredMixin, View):
    template_name = 'inventory/order_create.html'

    def get(self, request, *args, **kwargs):
        context = {
            'warehouses': Warehouse.objects.filter(is_active=True),
            'products': Product.objects.filter(is_active=True).select_related('unit_of_measure'),
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                if request.content_type == 'application/json':
                    data = json.loads(request.body)
                else:
                    data = request.POST

                order_number = data.get('order_number')
                warehouse_id = data.get('warehouse')
                
                if not warehouse_id:
                    return JsonResponse({
                        'success': False, 
                        'error': 'Warehouse is required'
                    }, status=400)

                if Order.objects.filter(order_number=order_number).exists():
                    return JsonResponse({
                        'success': False, 
                        'error': f'Order number {order_number} already exists'
                    }, status=400)

                # Get warehouse
                try:
                    warehouse = Warehouse.objects.get(id=warehouse_id, is_active=True)
                except Warehouse.DoesNotExist:
                    return JsonResponse({
                        'success': False, 
                        'error': 'Invalid warehouse'
                    }, status=400)

                # Create order
                order = Order.objects.create(
                    warehouse=warehouse,
                    created_by=request.user,
                    status='pending'
                )

                # Process order items
                if request.content_type == 'application/json':
                    order_items = data.get('order_items', [])
                    for item_data in order_items:
                        self._create_order_item(order, item_data)
                else:
                    product_ids = request.POST.getlist('product_id')
                    quantities = request.POST.getlist('quantity')
                    
                    for product_id, quantity in zip(product_ids, quantities):
                        if quantity and float(quantity) > 0:
                            self._create_order_item_from_form(order, product_id, quantity)

                try:
                    order.status = 'confirmed'
                    order.save()
                    self._update_stock_for_order(order)
                    
                    response_data = {
                        'success': True,
                        'message': f'Order {order.order_number} created successfully',
                        'order_id': order.id,
                        'order_number': order.order_number
                    }
                    
                    if request.content_type == 'application/json':
                        return JsonResponse(response_data)
                    else:
                        messages.success(request, response_data['message'])
                        return redirect('order-list')
                        
                except ValueError as e:
                    order.delete()
                    return JsonResponse({
                        'success': False, 
                        'error': str(e)
                    }, status=400)

        except Exception as e:
            return JsonResponse({
                'success': False, 
                'error': f'Error creating order: {str(e)}'
            }, status=500)

    def _create_order_item(self, order, item_data):
        """Create order item from JSON data"""
        product_id = item_data.get('product_id')
        quantity = item_data.get('quantity')
        
        if not product_id or not quantity:
            raise ValueError('Product ID and quantity are required for order items')
        
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise ValueError(f'Invalid product ID: {product_id}')
        
        if float(quantity) <= 0:
            raise ValueError(f'Quantity must be positive for product {product.sku}')
        
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity
        )

    def _create_order_item_from_form(self, order, product_id, quantity):
        """Create order item from form data"""
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise ValueError(f'Invalid product ID: {product_id}')
        
        if float(quantity) <= 0:
            raise ValueError(f'Quantity must be positive for product {product.sku}')
        
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity
        )

    def _update_stock_for_order(self, order):
        """Update stock quantities for confirmed order"""
        if order.status != 'confirmed':
            return
        
        for order_item in order.order_items.all():
            stock_item = StockItem.objects.filter(
                product=order_item.product,
                warehouse=order.warehouse
            ).first()
            
            if not stock_item:
                raise ValueError(f'No stock found for {order_item.product.sku} in warehouse {order.warehouse.code}')
            
            if stock_item.quantity < order_item.quantity:
                raise ValueError(f'Insufficient stock for {order_item.product.sku}. Available: {stock_item.quantity}, Required: {order_item.quantity}')
            
            # Create stock transaction
            StockTransaction.objects.create(
                stock_item=stock_item,
                transaction_type='out',
                quantity=order_item.quantity,
                reference=f"Order {order.order_number}",
                notes=f"Stock deducted for order {order.order_number}",
                created_by=order.created_by
            )
            
            # Update stock quantity
            stock_item.quantity -= order_item.quantity
            stock_item.save()
            
            # Check for low stock and create reorder alert if needed
            if stock_item.quantity <= stock_item.reorder_threshold and stock_item.quantity > 0:
                ReorderAlert.objects.get_or_create(
                    stock_item=stock_item,
                    defaults={
                        'triggered_by': order.created_by,
                        'status': 'active',
                        'notes': f"Low stock triggered by order {order.order_number}"
                    }
                )

class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'inventory/order_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        return Order.objects.select_related('warehouse', 'created_by').order_by('-created_at')

@require_POST
@login_required
def stock_adjustment_ajax(request):
    try:
        stock_item_id = (
            request.POST.get('stock_item_id') or 
            request.POST.get('stock_item')
        )
        
        quantity = request.POST.get('quantity')
        reference = request.POST.get('reference', '').strip()
        notes = request.POST.get('notes', '').strip()

        if not stock_item_id:
            return JsonResponse({
                'success': False, 
                'error': 'Stock item is required'
            }, status=400)
        
        if not quantity:
            return JsonResponse({'success': False, 'error': 'Quantity is required'}, status=400)

        try:
            quantity = Decimal(quantity)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Invalid quantity format'}, status=400)

        with db_transaction.atomic():
            stock_item = StockItem.objects.select_for_update().get(pk=stock_item_id)
            
            old_quantity = stock_item.quantity
            stock_item.quantity = quantity
            stock_item.save()
            
            quantity_difference = quantity - old_quantity
            
            if not reference:
                reference = f"Adjustment-{timezone.now().strftime('%Y%m%d-%H%M%S')}"
            
            # Create the transaction
            stock_transaction = StockTransaction.objects.create(
                stock_item=stock_item,
                transaction_type='adjustment',
                quantity=quantity_difference,
                reference=reference,
                notes=notes,
                created_by=request.user
            )
            
            try:
                if stock_item.unit_cost and quantity_difference != 0:
                    FinanceIntegrationService.create_stock_adjustment_entry(
                        stock_transaction=stock_transaction,
                        adjustment_amount=quantity_difference,
                        unit_cost=stock_item.unit_cost
                    )
            except Exception as finance_error:
                print(f"Finance integration skipped: {finance_error}")
            
            # Return success response
            return JsonResponse({
                'success': True,
                'message': 'Stock adjusted successfully.',
                'new_quantity': float(stock_item.quantity),
                'uom': stock_item.product.unit_of_measure.symbol,
            })
            
    except StockItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Stock item not found.'}, status=404)
    except Exception as e:
        if "transaction_id" in str(e).lower() or "finance" in str(e).lower():
            return JsonResponse({
                'success': True,
                'message': 'Stock adjusted successfully (finance integration pending)',
                'new_quantity': float(stock_item.quantity),
                'uom': stock_item.product.unit_of_measure.symbol,
            })
        else:
            return JsonResponse({'success': False, 'error': f'Server error: {str(e)}'}, status=400)

@require_POST
@login_required
def order_create_ajax(request):
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        warehouse_id = data.get('warehouse')
        notes = data.get('notes', '')

        if not items:
            return JsonResponse({'success': False, 'error': 'No items provided'}, status=400)

        warehouse = get_object_or_404(Warehouse, id=warehouse_id)

        with transaction.atomic():
            order = Order.objects.create(
                warehouse=warehouse,
                created_by=request.user,
                status='pending',
                notes=notes
            )

            for item in items:
                product = get_object_or_404(Product, id=item['product_id'])
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=Decimal(item['quantity'])
                )

        return JsonResponse({
            'success': True,
            'order_number': order.order_number,
            'order_id': order.id
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@method_decorator(login_required, name='dispatch')
class LowStockAPIView(View):
    def get(self, request):
        try:
            low_stock_items = StockItem.objects.filter(
                quantity__lte=F('reorder_threshold')
            ).select_related('product', 'warehouse')
            
            data = {
                'success': True,
                'count': low_stock_items.count(),
                'low_stock_items': [
                    {
                        'id': item.id,
                        'product_sku': item.product.sku,
                        'product_name': item.product.name,
                        'warehouse': item.warehouse.name,
                        'quantity': float(item.quantity),
                        'reorder_threshold': float(item.reorder_threshold),
                        'unit_cost': float(item.unit_cost),
                        'total_value': float(item.total_value),
                        'batch_number': item.batch_number,
                        'location': item.location,
                        'is_expired': item.is_expired,
                        'usage_rate': float(item.usage_rate),
                        'forecast_reorder_date': item.forecast_reorder_date.strftime('%Y-%m-%d') if item.forecast_reorder_date else None,
                        'procurement_status': item.procurement_status,
                    }
                    for item in low_stock_items
                ]
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

@method_decorator(login_required, name='dispatch')
class ProcurementUpdateAPIView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            stock_item_id = data.get('stock_item_id')
            new_status = data.get('procurement_status')
            stock_item = StockItem.objects.get(id=stock_item_id)
            
            if new_status in ['none', 'pending', 'ordered', 'delivered']:
                stock_item.procurement_status = new_status
                stock_item.save()
                
                # Create or update reorder alert
                if new_status in ['pending', 'ordered']:
                    ReorderAlert.objects.get_or_create(
                        stock_item=stock_item,
                        defaults={'triggered_by': request.user, 'status': 'active'}
                    )
                elif new_status == 'delivered':
                    ReorderAlert.objects.filter(stock_item=stock_item, status='active').update(
                        status='resolved', notes=f"Resolved on {timezone.now().date()}"
                    )
                
                return JsonResponse({'success': True, 'message': 'Procurement status updated'})
            else:
                return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
        except StockItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Stock item not found'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

@method_decorator(login_required, name='dispatch')
class DashboardDataAPIView(View):
    def get(self, request):
        try:
            # Fetch summary statistics
            stock_items = StockItem.objects.select_related('product', 'warehouse')
            total_items = stock_items.count()
            total_value = sum(float(item.total_value) for item in stock_items)
            low_stock_count = stock_items.filter(quantity__lte=F('reorder_threshold')).count()
            out_of_stock_count = stock_items.filter(quantity__lte=0).count()
            reorder_alert_count = ReorderAlert.objects.filter(status='active').count()

            # Stock status for chart
            stock_status = stock_items.aggregate(
                in_stock=Count('id', filter=~Q(quantity__lte=F('reorder_threshold')) & ~Q(quantity__lte=0)),
                low_stock=Count('id', filter=Q(quantity__lte=F('reorder_threshold')) & ~Q(quantity__lte=0)),
                out_of_stock=Count('id', filter=Q(quantity__lte=0))
            )

            recent_items = stock_items.order_by('product__sku', 'batch_number')[:10]

            data = {
                'success': True,
                'total_items': total_items,
                'total_value': float(total_value),
                'low_stock_count': low_stock_count,
                'out_of_stock_count': out_of_stock_count,
                'reorder_alert_count': reorder_alert_count,
                'stock_status': stock_status,
                'stock_items': [
                    {
                        'id': item.id,
                        'product_sku': item.product.sku,
                        'product_name': item.product.name,
                        'batch_number': item.batch_number or '-',
                        'warehouse_code': item.warehouse.code,
                        'quantity': float(item.quantity),
                        'unit_of_measure': item.product.unit_of_measure.symbol,
                        'total_value': float(item.total_value),
                        'is_low_stock': item.is_low_stock,
                        'is_out_of_stock': item.quantity <= 0,
                    } for item in recent_items
                ]
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

class PrintLabelView(LoginRequiredMixin, DetailView):
    model = StockItem

    def get(self, request, *args, **kwargs):
        item = self.get_object()
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{item.product.sku}_label.pdf"'
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
                counted = Decimal(request.POST['counted_quantity'])
                notes = request.POST.get('notes', '')
                diff = counted - stock_item.quantity
                if diff != 0:
                    StockTransaction.objects.create(
                        stock_item=stock_item,
                        transaction_type='adjustment',
                        quantity=diff,
                        reference='Stock Count Adjustment',
                        notes=notes,
                        created_by=request.user
                    )
                return JsonResponse({'success': True, 'message': 'Stock count submitted.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

class QualityCheckCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            stock_item = StockItem.objects.get(id=pk)
            status = request.POST['status']
            notes = request.POST['notes']
            StockTransaction.objects.create(
                stock_item=stock_item,
                transaction_type='quality',
                quantity=0,  
                reference=f'Quality Check: {status.upper()}',
                notes=notes,
                created_by=request.user
            )
            return JsonResponse({'success': True, 'message': 'Quality check submitted.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

