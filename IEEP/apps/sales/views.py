# sales/views.py
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction as db_transaction
from django.utils import timezone
from datetime import timedelta 
from django.db.models import Q, Sum, Count
from decimal import Decimal
import json

from .models import Customer, SalesInquiry, SalesInquiryItem, SaleOrder, SaleOrderItem, Invoice
from .forms import (
    CustomerForm, SalesInquiryForm, SalesInquiryItemForm,
    SaleOrderForm, SaleOrderItemForm, SalesInquiryItemFormSet,
    SaleOrderItemFormSet
)
from apps.inventory.models import StockItem, StockTransaction, Warehouse
from apps.products.models import Product

class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer
    template_name = 'sales/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Customer.objects.all().select_related('registered_by')
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search) |
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )
        
        customer_type = self.request.GET.get('customer_type')
        if customer_type:
            queryset = queryset.filter(customer_type=customer_type)
        
        status = self.request.GET.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        customer_stats = Customer.objects.aggregate(
            total_customers=Count('id'),
            active_customers=Count('id', filter=Q(is_active=True)),
        )
        
        context.update(customer_stats)
        return context

class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'sales/customer_form.html'
    success_url = reverse_lazy('customer-list')
    
    def form_valid(self, form):
        form.instance.registered_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f'Customer {self.object.code} created successfully!')
        return response

class CustomerDetailView(LoginRequiredMixin, DetailView):
    model = Customer
    template_name = 'sales/customer_detail.html'
    context_object_name = 'customer'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = self.object
        context['recent_inquiries'] = customer.inquiries.order_by('-inquiry_date')[:5]
        context['recent_orders'] = customer.sale_orders.order_by('-order_date')[:5]
        context['total_orders'] = customer.sale_orders.count()
        context['total_order_value'] = customer.sale_orders.aggregate(
            total=Sum('grand_total')
        )['total'] or 0
        return context

class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'sales/customer_form.html'
    
    def get_success_url(self):
        return reverse('customer-detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Customer {self.object.code} updated successfully!')
        return response

class CustomerToggleActiveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        customer.is_active = not customer.is_active
        customer.save()
        
        action = "activated" if customer.is_active else "deactivated"
        messages.success(request, f'Customer {customer.code} {action} successfully!')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'is_active': customer.is_active,
                'message': f'Customer {action} successfully!'
            })
        
        return redirect('customer-detail', pk=customer.pk)

class SalesInquiryListView(LoginRequiredMixin, ListView):
    model = SalesInquiry
    template_name = 'sales/sales_inquiry_list.html'
    context_object_name = 'inquiries'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = SalesInquiry.objects.select_related(
            'customer', 'requested_by', 'inventory_checked_by'
        ).prefetch_related('items')
        
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        customer_id = self.request.GET.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(inquiry_number__icontains=search) |
                Q(customer__name__icontains=search) |
                Q(customer__code__icontains=search)
            )
        
        return queryset.order_by('-inquiry_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['customers'] = Customer.objects.filter(is_active=True)
        
        status_counts = SalesInquiry.objects.values('status').annotate(
            count=Count('id')
        )
        context['status_counts'] = {
            item['status']: item['count'] for item in status_counts
        }
        
        return context

class SalesInquiryCreateView(LoginRequiredMixin, CreateView):
    model = SalesInquiry
    form_class = SalesInquiryForm
    template_name = 'sales/sales_inquiry_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['today'] = timezone.now().date()
        
        if self.request.POST:
            context['formset'] = SalesInquiryItemFormSet(self.request.POST)
        else:
            context['formset'] = SalesInquiryItemFormSet()
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        if formset.is_valid():
            try:
                with db_transaction.atomic():
                    form.instance.requested_by = self.request.user
                    self.object = form.save()
                    
                    formset.instance = self.object
                    formset.save()
                    
                    self.object.calculate_totals()
                    self.object.save()
                    
                    messages.success(
                        self.request, 
                        f'Sales inquiry {self.object.inquiry_number} created successfully!'
                    )
                    return redirect('sales-inquiry-detail', pk=self.object.pk)
                    
            except Exception as e:
                messages.error(self.request, f'Error creating sales inquiry: {str(e)}')
                return self.form_invalid(form)
        else:
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return self.render_to_response(self.get_context_data(form=form))

class SalesInquiryDetailView(LoginRequiredMixin, DetailView):
    model = SalesInquiry
    template_name = 'sales/sales_inquiry_detail.html'
    context_object_name = 'inquiry'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inquiry = self.object
        
        context['items'] = inquiry.items.select_related(
            'product', 'suggested_warehouse', 'suggested_stock_item'
        )
        
        context['can_submit'] = (
            inquiry.status == 'draft' and 
            inquiry.items.exists()
        )
        
        context['can_check_inventory'] = (
            inquiry.status == 'submitted'
        )
        
        context['can_approve'] = (
            inquiry.status == 'submitted' and 
            inquiry.can_be_approved
        )
        
        context['can_edit'] = (inquiry.status == 'draft')
        context['can_cancel'] = (inquiry.status in ['draft', 'submitted'])
        context['can_convert'] = (inquiry.status == 'approved' and not hasattr(inquiry, 'sale_order'))
        
        return context

class SalesInquiryUpdateView(LoginRequiredMixin, UpdateView):
    model = SalesInquiry
    form_class = SalesInquiryForm
    template_name = 'sales/sales_inquiry_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['today'] = timezone.now().date()
        
        if self.request.POST:
            context['formset'] = SalesInquiryItemFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context['formset'] = SalesInquiryItemFormSet(instance=self.object)
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        if self.object.status != 'draft':
            messages.error(self.request, 'Only draft inquiries can be edited.')
            return redirect('sales-inquiry-detail', pk=self.object.pk)
        
        with db_transaction.atomic():
            if formset.is_valid():
                self.object = form.save()
                formset.instance = self.object
                formset.save()
                
                self.object.calculate_totals()
                self.object.save()
                
                messages.success(
                    self.request, 
                    f'Sales inquiry {self.object.inquiry_number} updated successfully!'
                )
                return redirect('sales-inquiry-detail', pk=self.object.pk)
        
        return self.form_invalid(form)

class SalesInquirySubmitView(LoginRequiredMixin, View):
    def post(self, request, pk):
        inquiry = get_object_or_404(SalesInquiry, pk=pk)
        
        if not inquiry.can_be_submitted:
            messages.error(request, 'Cannot submit inquiry. Check if it has items and is in draft status.')
            return redirect('sales-inquiry-detail', pk=inquiry.pk)
        
        inquiry.status = 'submitted'
        inquiry.save()
        
        messages.success(request, f'Inquiry {inquiry.inquiry_number} submitted for inventory check!')
        return redirect('sales-inquiry-detail', pk=inquiry.pk)

class CheckInventoryView(LoginRequiredMixin, View):
    def post(self, request, pk):
        inquiry = get_object_or_404(SalesInquiry, pk=pk, status='submitted')
        
        try:
            with db_transaction.atomic():
                all_available = True
                inventory_response = []
                
                for item in inquiry.items.all():
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
                
                if all_available:
                    inquiry.status = 'approved'
                    message = 'All products available. Inquiry approved!'
                else:
                    inquiry.status = 'rejected'
                    message = 'Some products unavailable. Inquiry rejected.'
                
                inquiry.save()
                
                messages.success(request, message)
                return redirect('sales-inquiry-detail', pk=inquiry.pk)
                
        except Exception as e:
            messages.error(request, f'Error checking inventory: {str(e)}')
            return redirect('sales-inquiry-detail', pk=inquiry.pk)

class ApproveInquiryView(LoginRequiredMixin, View):
    def post(self, request, pk):
        inquiry = get_object_or_404(SalesInquiry, pk=pk, status='submitted')
        
        if not inquiry.can_be_approved:
            messages.error(request, 'Cannot approve inquiry - not all items are available.')
            return redirect('sales-inquiry-detail', pk=inquiry.pk)
        
        inquiry.status = 'approved'
        inquiry.inventory_checked_by = request.user
        inquiry.inventory_responded_at = timezone.now()
        inquiry.save()
        
        messages.success(request, f'Inquiry {inquiry.inquiry_number} approved!')
        return redirect('sales-inquiry-detail', pk=inquiry.pk)

class SalesInquiryCancelView(LoginRequiredMixin, View):
    def post(self, request, pk):
        inquiry = get_object_or_404(SalesInquiry, pk=pk)
        
        if inquiry.status not in ['draft', 'submitted']:
            messages.error(request, 'Cannot cancel inquiry in current status.')
            return redirect('sales-inquiry-detail', pk=inquiry.pk)
        
        inquiry.status = 'cancelled'
        inquiry.save()
        
        messages.success(request, f'Inquiry {inquiry.inquiry_number} cancelled.')
        return redirect('sales-inquiry-detail', pk=inquiry.pk)

class SaleOrderListView(LoginRequiredMixin, ListView):
    model = SaleOrder
    template_name = 'sales/sale_order_list.html'
    context_object_name = 'sale_orders'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = SaleOrder.objects.select_related(
            'customer', 'warehouse', 'created_by', 'inquiry'
        ).prefetch_related('items')
        
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        customer_id = self.request.GET.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        
        warehouse_id = self.request.GET.get('warehouse')
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search) |
                Q(customer__name__icontains=search) |
                Q(customer__code__icontains=search)
            )
        
        return queryset.order_by('-order_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['customers'] = Customer.objects.filter(is_active=True)
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        
        status_counts = SaleOrder.objects.values('status').annotate(
            count=Count('id')
        )
        context['status_counts'] = {
            item['status']: item['count'] for item in status_counts
        }
        
        return context

class SaleOrderCreateView(LoginRequiredMixin, CreateView):
    model = SaleOrder
    form_class = SaleOrderForm
    template_name = 'sales/sale_order_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['today'] = timezone.now().date()
        
        if self.request.POST:
            context['formset'] = SaleOrderItemFormSet(self.request.POST)
        else:
            context['formset'] = SaleOrderItemFormSet()
        
        context['creating_from_inquiry'] = False
        context['inquiry'] = None

        inquiry_id = self.request.GET.get('from_inquiry')
        if inquiry_id:
            try:
                inquiry = SalesInquiry.objects.get(pk=inquiry_id, status='approved')
                context['inquiry'] = inquiry
                context['creating_from_inquiry'] = True

                if self.request.method == 'GET':
                    initial_data = {
                        'customer': inquiry.customer_id,
                        'expected_ship_date': inquiry.required_date,
                        'notes': inquiry.notes,
                    }
                    context['form'] = SaleOrderForm(initial=initial_data)

                    item_data = []
                    for item in inquiry.items.all():
                        unit_price = item.unit_price or getattr(item.product, 'selling_price', 0)
                        item_data.append({
                            'product': item.product_id,
                            'quantity': item.quantity,
                            'unit_price': unit_price if unit_price else 0,
                            'discount_percent': 0,
                        })
                    context['formset'] = SaleOrderItemFormSet(initial=item_data)
                    
            except SalesInquiry.DoesNotExist:
                messages.error(self.request, "Invalid or unavailable inquiry.")
        
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        if formset.is_valid():
            try:
                with db_transaction.atomic():
                    form.instance.created_by = self.request.user
                    
                    # Determine the action
                    action = self.request.POST.get('action')
                    
                    # Set status based on action
                    if action == 'submit_order':
                        form.instance.status = 'confirmed'
                    else:  # save_draft or default
                        form.instance.status = 'draft'
                    
                    self.object = form.save()

                    formset.instance = self.object
                    formset.save()

                    # AUTO-ASSIGN STOCK ITEMS FOR DRAFT ORDERS
                    if self.object.status == 'draft':
                        self._assign_stock_items(self.object)

                    self.object.calculate_totals()
                    self.object.save()

                    # If confirming order, deduct stock
                    if self.object.status == 'confirmed':
                        self._deduct_stock_from_order(self.object, self.request.user)

                    inquiry_id = self.request.GET.get('from_inquiry') or self.request.POST.get('inquiry_id')
                    if inquiry_id:
                        try:
                            inquiry = SalesInquiry.objects.get(pk=inquiry_id)
                            inquiry.status = 'converted'
                            inquiry.save()
                        except SalesInquiry.DoesNotExist:
                            pass

                if action == 'submit_order':
                    messages.success(
                        self.request, 
                        f'Sale Order {self.object.order_number} created and confirmed successfully! Stock has been deducted from inventory.'
                    )
                else:
                    messages.success(
                        self.request, 
                        f'Sale Order {self.object.order_number} saved as draft successfully!'
                    )
                    
                return redirect('sale-order-detail', pk=self.object.pk)
                
            except Exception as e:
                messages.error(self.request, f'Error creating sale order: {str(e)}')
                return self.form_invalid(form)
        else:
            return self.form_invalid(form)

    def _assign_stock_items(self, sale_order):
        """Auto-assign stock items to order items for draft orders"""
        for item in sale_order.items.all():
            if not item.stock_item:
                available_stock = StockItem.objects.filter(
                    product=item.product,
                    warehouse=sale_order.warehouse,
                    quantity__gte=item.quantity
                ).first()
                
                if available_stock:
                    item.stock_item = available_stock
                    item.save()

    def _deduct_stock_from_order(self, sale_order, user):
        """Deduct stock from inventory for confirmed orders"""
        for item in sale_order.items.all():
            if item.stock_item:
                StockTransaction.objects.create(
                    stock_item=item.stock_item,
                    transaction_type='out',
                    quantity=item.quantity,
                    reference=f"Sale {sale_order.order_number}",
                    notes=f"Sold to {sale_order.customer.name}",
                    created_by=user
                )

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return self.render_to_response(self.get_context_data(form=form))

class SaleOrderDetailView(LoginRequiredMixin, DetailView):
    model = SaleOrder
    template_name = 'sales/sale_order_detail.html'
    context_object_name = 'sale_order'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sale_order = self.object
        
        context['items'] = sale_order.items.select_related(
            'product', 'stock_item', 'stock_item__warehouse'
        )
        
        context['can_edit'] = (sale_order.status == 'draft')
        context['can_confirm'] = (sale_order.status == 'draft' and sale_order.can_be_confirmed)
        context['can_ship'] = (sale_order.status == 'confirmed')
        context['can_deliver'] = (sale_order.status == 'shipped')
        context['can_cancel'] = (sale_order.status in ['draft', 'confirmed'])
        context['can_create_invoice'] = (
            sale_order.status in ['confirmed', 'shipped', 'delivered'] and 
            not hasattr(sale_order, 'invoice')
        )
        
        return context

class SaleOrderUpdateView(LoginRequiredMixin, UpdateView):
    model = SaleOrder
    form_class = SaleOrderForm
    template_name = 'sales/sale_order_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if self.request.POST:
            context['formset'] = SaleOrderItemFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context['formset'] = SaleOrderItemFormSet(instance=self.object)
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        if self.object.status != 'draft':
            messages.error(self.request, 'Only draft orders can be edited.')
            return redirect('sale-order-detail', pk=self.object.pk)
        
        with db_transaction.atomic():
            # Determine the action
            action = self.request.POST.get('action')
            
            # Set status based on action
            if action == 'submit_order':
                form.instance.status = 'confirmed'
            
            self.object = form.save()
            
            if formset.is_valid():
                formset.save()
                
                self.object.calculate_totals()
                self.object.save()
                
                if action == 'submit_order':
                    messages.success(
                        self.request, 
                        f'Sale order {self.object.order_number} updated and confirmed successfully!'
                    )
                else:
                    messages.success(
                        self.request, 
                        f'Sale order {self.object.order_number} updated successfully!'
                    )
                return redirect('sale-order-detail', pk=self.object.pk)
            else:
                return self.form_invalid(form)

class SaleOrderConfirmView(LoginRequiredMixin, View):
    def post(self, request, pk):
        sale_order = get_object_or_404(SaleOrder, pk=pk, status='draft')
        
        try:
            with db_transaction.atomic():
                # Method 1: Direct stock update (more reliable)
                for item in sale_order.items.all():
                    # Find and lock the stock item for update
                    stock_item = StockItem.objects.select_for_update().get(
                        product=item.product,
                        warehouse=sale_order.warehouse
                    )
                    
                    # Check stock availability
                    if stock_item.quantity < item.quantity:
                        messages.error(
                            request, 
                            f'Insufficient stock for {item.product.sku}. Available: {stock_item.quantity}, Required: {item.quantity}'
                        )
                        return redirect('sale-order-detail', pk=sale_order.pk)
                    
                    # Directly update stock quantity
                    stock_item.quantity -= item.quantity
                    stock_item.save()
                    
                    # Assign to order item
                    item.stock_item = stock_item
                    item.save()
                    
                    # Also create transaction record for audit
                    StockTransaction.objects.create(
                        stock_item=stock_item,
                        transaction_type='out',
                        quantity=item.quantity,
                        reference=f"SO-{sale_order.order_number}",
                        notes=f"Sale to {sale_order.customer.name}",
                        created_by=request.user
                    )
                
                # Update order status
                sale_order.status = 'confirmed'
                sale_order.save()
                
                messages.success(
                    request, 
                    f'Sale order {sale_order.order_number} confirmed! Stock deducted directly.'
                )
                return redirect('sale-order-detail', pk=sale_order.pk)
                
        except StockItem.DoesNotExist:
            messages.error(request, 'Stock item not found for one or more products.')
            return redirect('sale-order-detail', pk=sale_order.pk)
        except Exception as e:
            messages.error(request, f'Error confirming sale order: {str(e)}')
            return redirect('sale-order-detail', pk=sale_order.pk)

class SaleOrderShipView(LoginRequiredMixin, View):
    def post(self, request, pk):
        sale_order = get_object_or_404(SaleOrder, pk=pk, status='confirmed')
        
        sale_order.status = 'shipped'
        sale_order.actual_ship_date = timezone.now().date()
        sale_order.save()
        
        messages.success(request, f'Sale order {sale_order.order_number} marked as shipped!')
        return redirect('sale-order-detail', pk=sale_order.pk)

class SaleOrderDeliverView(LoginRequiredMixin, View):
    def post(self, request, pk):
        sale_order = get_object_or_404(SaleOrder, pk=pk, status='shipped')
        
        sale_order.status = 'delivered'
        sale_order.delivery_date = timezone.now().date()
        sale_order.save()
        
        messages.success(request, f'Sale order {sale_order.order_number} marked as delivered!')
        return redirect('sale-order-detail', pk=sale_order.pk)

class SaleOrderCancelView(LoginRequiredMixin, View):
    def post(self, request, pk):
        sale_order = get_object_or_404(SaleOrder, pk=pk)
        
        if sale_order.status not in ['draft', 'confirmed']:
            messages.error(request, 'Cannot cancel order in current status.')
            return redirect('sale-order-detail', pk=sale_order.pk)
        
        if sale_order.status == 'confirmed':
            try:
                with db_transaction.atomic():
                    for item in sale_order.items.all():
                        if item.stock_item:
                            StockTransaction.objects.create(
                                stock_item=item.stock_item,
                                transaction_type='in',
                                quantity=item.quantity,
                                reference=f"Order Cancellation {sale_order.order_number}",
                                notes=f"Stock restored due to order cancellation",
                                created_by=request.user
                            )
            except Exception as e:
                messages.error(request, f'Error restoring stock: {str(e)}')
                return redirect('sale-order-detail', pk=sale_order.pk)
        
        sale_order.status = 'cancelled'
        sale_order.save()
        
        messages.success(request, f'Sale order {sale_order.order_number} cancelled.')
        return redirect('sale-order-detail', pk=sale_order.pk)

class CreateInvoiceView(LoginRequiredMixin, View):
    def post(self, request, pk):
        sale_order = get_object_or_404(SaleOrder, pk=pk)
        
        if hasattr(sale_order, 'invoice'):
            messages.error(request, 'Invoice already exists for this order.')
            return redirect('sale-order-detail', pk=sale_order.pk)
        
        if sale_order.status not in ['confirmed', 'shipped', 'delivered']:
            messages.error(request, 'Cannot create invoice for order in current status.')
            return redirect('sale-order-detail', pk=sale_order.pk)
        
        try:
            with db_transaction.atomic():
                due_date = timezone.now().date() + timedelta(
                    days=sale_order.customer.payment_terms
                )
                
                invoice = Invoice.objects.create(
                    sale_order=sale_order,
                    customer=sale_order.customer,
                    invoice_date=timezone.now().date(),
                    due_date=due_date,
                    total_amount=sale_order.grand_total,
                    tax_amount=sale_order.tax_amount,
                    created_by=request.user
                )
                
                sale_order.status = 'invoiced'
                sale_order.save()
                
                messages.success(
                    request, 
                    f'Invoice {invoice.invoice_number} created successfully!'
                )
                return redirect('sale-order-detail', pk=sale_order.pk)
                
        except Exception as e:
            messages.error(request, f'Error creating invoice: {str(e)}')
            return redirect('sale-order-detail', pk=sale_order.pk)

# AJAX Views
def customer_search_ajax(request):
    search = request.GET.get('search', '')
    customers = Customer.objects.filter(
        Q(name__icontains=search) |
        Q(code__icontains=search) |
        Q(email__icontains=search)
    )[:10]
    
    results = []
    for customer in customers:
        results.append({
            'id': customer.id,
            'text': f"{customer.code} - {customer.name}",
            'code': customer.code,
            'name': customer.name,
        })
    
    return JsonResponse({'results': results})

def product_search_ajax(request):
    search_term = request.GET.get('search', '').strip()
    queryset = Product.objects.filter(is_active=True).select_related('unit_of_measure')

    if search_term:
        queryset = queryset.filter(
            Q(sku__icontains=search_term) |
            Q(name__icontains=search_term)
        )

    products = queryset[:10]

    results = [
        {
            'id': p.id,
            'text': f"{p.sku} - {p.name}",
            'sku': p.sku,
            'name': p.name,
            'selling_price': float(p.selling_price) if p.selling_price else 0.0,
            'unit': p.unit_of_measure.symbol if p.unit_of_measure else '',
        }
        for p in products
    ]

    return JsonResponse({'results': results})

def stock_check_ajax(request):
    product_id = request.GET.get('product_id')
    quantity = Decimal(request.GET.get('quantity', 0))
    warehouse_id = request.GET.get('warehouse_id')
    
    if not product_id or quantity <= 0:
        return JsonResponse({'error': 'Invalid parameters'})
    
    try:
        product = Product.objects.get(id=product_id)
        
        if warehouse_id:
            available_stock = StockItem.objects.filter(
                product=product,
                warehouse_id=warehouse_id,
                quantity__gte=quantity
            ).select_related('warehouse').first()
        else:
            available_stock = StockItem.objects.filter(
                product=product,
                quantity__gte=quantity
            ).select_related('warehouse').first()
        
        if available_stock:
            return JsonResponse({
                'available': True,
                'warehouse': available_stock.warehouse.code,
                'warehouse_name': available_stock.warehouse.name,
                'available_quantity': float(available_stock.quantity),
                'stock_item_id': available_stock.id,
            })
        else:
            if warehouse_id:
                total_stock = StockItem.objects.filter(
                    product=product,
                    warehouse_id=warehouse_id
                ).aggregate(total=Sum('quantity'))['total'] or 0
            else:
                total_stock = StockItem.objects.filter(
                    product=product
                ).aggregate(total=Sum('quantity'))['total'] or 0
            
            return JsonResponse({
                'available': False,
                'total_available': float(total_stock),
                'message': f'Insufficient stock. Available: {total_stock}'
            })
            
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'})

class SalesDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'sales/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['total_customers'] = Customer.objects.count()
        context['total_inquiries'] = SalesInquiry.objects.count()
        context['total_orders'] = SaleOrder.objects.count()
        context['pending_inquiries'] = SalesInquiry.objects.filter(status='submitted').count()
        context['pending_orders'] = SaleOrder.objects.filter(status='draft').count()
        context['active_customers'] = Customer.objects.filter(is_active=True).count()
        
        today = timezone.now().date()
        month_start = today.replace(day=1)
        
        monthly_sales = SaleOrder.objects.filter(
            order_date__date__gte=month_start,
            status__in=['confirmed', 'shipped', 'delivered', 'invoiced']
        ).aggregate(total=Sum('grand_total'))['total'] or 0
        
        context['monthly_sales'] = monthly_sales
        context['recent_inquiries'] = SalesInquiry.objects.select_related('customer').order_by('-inquiry_date')[:5]
        context['recent_orders'] = SaleOrder.objects.select_related('customer').order_by('-order_date')[:5]
        
        return context