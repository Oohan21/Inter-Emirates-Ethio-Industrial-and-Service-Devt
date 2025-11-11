from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.forms import modelformset_factory, inlineformset_factory
from django.forms.widgets import Select, NumberInput, TextInput, Textarea
from django.shortcuts import redirect, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils import timezone
from django.db import models
from .models import Supplier, PurchaseOrder, PurchaseOrderItem, PurchaseRequisition, PurchaseRequisitionItem, GoodsReceipt, GoodsReceiptItem
from .forms import SupplierForm
from apps.products.models import Product
from django.contrib.auth.mixins import LoginRequiredMixin
import uuid

# Supplier Views
@method_decorator(login_required, name='dispatch')
class SupplierListView(ListView):
    model = Supplier
    template_name = 'procurement/supplier_list.html'
    context_object_name = 'suppliers'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        supplier_type = self.request.GET.get('supplier_type')
        
        if search:
            queryset = queryset.filter(
                models.Q(code__icontains=search) |
                models.Q(name__icontains=search) |
                models.Q(contact_person__icontains=search)
            )
        
        if supplier_type:
            queryset = queryset.filter(supplier_type=supplier_type)
            
        return queryset

@method_decorator(login_required, name='dispatch')
class SupplierDetailView(DetailView):
    model = Supplier
    template_name = 'procurement/supplier_detail.html'
    context_object_name = 'supplier'

@method_decorator(login_required, name='dispatch')
class SupplierCreateView(CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'procurement/supplier_form.html'
    success_url = reverse_lazy('supplier-list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create New Supplier'
        return context
    
    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True, 
                'message': 'Supplier created successfully!',
                'redirect_url': self.success_url
            })
        else:
            messages.success(self.request, 'Supplier created successfully!')
            return response
    
    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False, 
                'errors': form.errors
            }, status=400)
        else:
            return super().form_invalid(form)

@method_decorator(login_required, name='dispatch')
class SupplierUpdateView(UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'procurement/supplier_form.html'
    success_url = reverse_lazy('supplier-list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Supplier: {self.object.code}'
        return context

# Purchase Order Views
@method_decorator(login_required, name='dispatch')
class PurchaseOrderListView(ListView):
    model = PurchaseOrder
    template_name = 'procurement/purchase_order_list.html'
    context_object_name = 'purchase_orders'
    ordering = ['-created_at']

@method_decorator(login_required, name='dispatch')
class PurchaseOrderDetailView(DetailView):
    model = PurchaseOrder
    template_name = 'procurement/purchase_order_detail.html'
    context_object_name = 'purchase_order'

@method_decorator(login_required, name='dispatch')
class PurchaseOrderCreateView(CreateView):
    model = PurchaseOrder
    template_name = 'procurement/purchase_order_form.html'
    fields = ['supplier', 'order_date', 'expected_delivery_date', 'terms_and_conditions']
    success_url = reverse_lazy('purchase-order-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = PurchaseOrderItemFormSet(self.request.POST)
        else:
            context['formset'] = PurchaseOrderItemFormSet()
        context['title'] = 'Create Purchase Order'
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        if formset.is_valid():
            form.instance.po_number = f'PO-{uuid.uuid4().hex[:8].upper()}'
            form.instance.created_by = self.request.user
            form.instance.status = 'draft'
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            
            # Calculate total amount
            self.object.total_amount = sum(
                item.quantity * item.unit_price for item in self.object.items.all()
            )
            self.object.save()
            
            if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'redirect_url': self.get_success_url()})
            else:
                messages.success(self.request, 'Purchase order created successfully!')
                return redirect(self.get_success_url())
        
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': formset.errors}, status=400)
        else:
            return self.form_invalid(form)

    def form_invalid(self, form):
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
        else:
            return super().form_invalid(form)

@method_decorator(login_required, name='dispatch')
class PurchaseOrderUpdateView(UpdateView):
    model = PurchaseOrder
    template_name = 'procurement/purchase_order_form.html'
    fields = ['supplier', 'order_date', 'expected_delivery_date', 'terms_and_conditions']
    success_url = reverse_lazy('purchase-order-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = PurchaseOrderItemFormSet(self.request.POST, instance=self.object)
        else:
            context['formset'] = PurchaseOrderItemFormSet(instance=self.object)
        context['title'] = f'Edit Purchase Order: {self.object.po_number}'
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            
            # Calculate total amount
            self.object.total_amount = sum(
                item.quantity * item.unit_price for item in self.object.items.all()
            )
            self.object.save()
            
            messages.success(self.request, 'Purchase order updated successfully!')
            return redirect(self.get_success_url())
        return self.form_invalid(form)

@method_decorator(login_required, name='dispatch')
class PurchaseOrderSendView(View):
    """View to send a purchase order to supplier"""
    
    def post(self, request, pk):
        purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
        
        # Check if PO is in draft status
        if purchase_order.status != 'draft':
            return JsonResponse({
                'success': False,
                'error': f'Cannot send purchase order with status: {purchase_order.get_status_display()}'
            }, status=400)
        
        # Check if PO has items
        if not purchase_order.items.exists():
            return JsonResponse({
                'success': False,
                'error': 'Cannot send purchase order without items'
            }, status=400)
        
        try:
            # Update status to 'sent'
            purchase_order.status = 'sent'
            purchase_order.updated_at = timezone.now()
            purchase_order.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Purchase order sent to supplier successfully',
                'new_status': purchase_order.status,
                'new_status_display': purchase_order.get_status_display()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error sending purchase order: {str(e)}'
            }, status=500)

# Purchase Requisition Views
@method_decorator(login_required, name='dispatch')
class PurchaseRequisitionListView(ListView):
    model = PurchaseRequisition
    template_name = 'procurement/requisition_list.html'
    context_object_name = 'requisitions'
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        
        if search:
            queryset = queryset.filter(requisition_number__icontains=search)
        
        if status:
            queryset = queryset.filter(status=status)
            
        return queryset

@method_decorator(login_required, name='dispatch')
class PurchaseRequisitionDetailView(DetailView):
    model = PurchaseRequisition
    template_name = 'procurement/requisition_detail.html'
    context_object_name = 'requisition'

@method_decorator(login_required, name='dispatch')
class PurchaseRequisitionCreateView(CreateView):
    model = PurchaseRequisition
    template_name = 'procurement/requisition_form.html'
    fields = ['department', 'purpose']
    success_url = reverse_lazy('requisition-list')
    
    def form_valid(self, form):
        form.instance.requisition_number = f'REQ-{uuid.uuid4().hex[:8].upper()}'
        form.instance.requested_by = self.request.user
        form.instance.status = 'draft'
        return super().form_valid(form)

# Goods Receipt Views
@method_decorator(login_required, name='dispatch')
class GoodsReceiptListView(ListView):
    model = GoodsReceipt
    template_name = 'procurement/goods_receipt_list.html'
    context_object_name = 'goods_receipts'
    ordering = ['-created_at']

@method_decorator(login_required, name='dispatch')
class GoodsReceiptDetailView(DetailView):
    model = GoodsReceipt
    template_name = 'procurement/goods_receipt_detail.html'
    context_object_name = 'goods_receipt'

@method_decorator(login_required, name='dispatch')
class GoodsReceiptCreateView(CreateView):
    model = GoodsReceipt
    template_name = 'procurement/goods_receipt_form.html'
    fields = ['purchase_order', 'received_by', 'receipt_date', 'notes']
    success_url = reverse_lazy('goods-receipt-list')
    
    def form_valid(self, form):
        form.instance.gr_number = f'GR-{uuid.uuid4().hex[:8].upper()}'
        return super().form_valid(form)

# Inline formset for PurchaseOrderItem
PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderItem,
    fields=['product', 'quantity', 'unit_price'],
    extra=1,
    can_delete=True,
    widgets={
        'product': Select(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm'}),
        'quantity': NumberInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'step': '0.0001'}),
        'unit_price': NumberInput(attrs={'class': 'w-full rounded-md border-gray-300 shadow-sm', 'step': '0.01'}),
    }
)