from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from .models import Product, Category, BOM, BOMComponent
from .forms import ProductForm, BOMForm, BOMComponentFormSet

@method_decorator(login_required, name='dispatch')
class ProductListView(ListView):
    model = Product
    template_name = 'products/product_list.html'
    context_object_name = 'products'
    paginate_by = 20
    ordering = ['sku']

    def get_queryset(self):
        queryset = super().get_queryset()
        
        product_type = self.request.GET.get('product_type')
        if product_type:
            queryset = queryset.filter(product_type=product_type)
        
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category__name=category)
        
        status = self.request.GET.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)
        
        return queryset

@method_decorator(login_required, name='dispatch')
class ProductDetailView(DetailView):
    model = Product
    template_name = 'products/product_detail.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        
        try:
            from inventory.models import StockItem
            stock_items = StockItem.objects.filter(product=product)
            context['total_stock'] = sum(item.quantity for item in stock_items)
            context['warehouse_count'] = stock_items.values('warehouse').distinct().count()
            if stock_items.exists():
                context['last_stock_update'] = stock_items.order_by('-updated_at').first().updated_at
            else:
                context['last_stock_update'] = None
        except:
            context['total_stock'] = 0
            context['warehouse_count'] = 0
            context['last_stock_update'] = None
        
        try:
            from production.models import ProductionOrder
            work_orders = ProductionOrder.objects.filter(product=product)
            context['work_order_count'] = work_orders.count()
            avg_yield = work_orders.aggregate(Avg('actual_yield'))['actual_yield__avg']
            context['average_yield'] = avg_yield or 0
            if work_orders.exists():
                context['last_production'] = work_orders.order_by('-created_at').first().created_at
            else:
                context['last_production'] = None
        except:
            context['work_order_count'] = 0
            context['average_yield'] = 0
            context['last_production'] = None
        
        return context

@method_decorator(login_required, name='dispatch')
class ProductCreateView(CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = '/products/'

    def form_valid(self, form):
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add New Product'
        return context

@method_decorator(login_required, name='dispatch')
class ProductUpdateView(UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = '/products/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Product: {self.object.sku}'
        return context

@method_decorator(login_required, name='dispatch')
class CategoryListView(ListView):
    model = Category
    template_name = 'products/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories_with_counts = []
        for category in context['categories']:
            categories_with_counts.append({
                'category': category,
                'finished_goods_count': category.finished_goods_count,
                'raw_materials_count': category.raw_materials_count,
                'intermediate_count': category.intermediate_count,
            })
        context['categories_with_counts'] = categories_with_counts
        return context

@method_decorator(login_required, name='dispatch')
class BOMListView(LoginRequiredMixin, ListView):
    model = BOM
    template_name = 'products/bom_list.html'
    context_object_name = 'boms'
    paginate_by = 20
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset().select_related('product', 'created_by')
        # Filters
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(is_active=(status == 'active'))

        product_id = self.request.GET.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)

        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(bom_code__icontains=search) |
                Q(product__sku__icontains=search) |
                Q(product__name__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['products'] = Product.objects.filter(is_active=True, product_type='finished')
        ctx['current_filters'] = self.request.GET.urlencode()
        return ctx

@method_decorator(login_required, name='dispatch')
class BOMCreateView(LoginRequiredMixin, CreateView):
    model = BOM
    form_class = BOMForm
    template_name = 'products/bom_form.html'
    success_url = reverse_lazy('bom-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['components'] = BOMComponentFormSet(self.request.POST)
        else:
            ctx['components'] = BOMComponentFormSet()
        return ctx

    def form_valid(self, form):
        context = self.get_context_data()
        components = context['components']

        with transaction.atomic():
            form.instance.created_by = self.request.user
            form.instance.is_draft = True   
            self.object = form.save()

            if components.is_valid():
                components.instance = self.object
                components.save()
                messages.success(self.request,
                                 f'BOM {self.object.bom_code} created (draft).')
            else:
                return self.form_invalid(form)

        return super().form_valid(form)

@method_decorator(login_required, name='dispatch')
class BOMPreviewView(LoginRequiredMixin, DetailView):
    model = BOM
    template_name = 'products/bom_detail.html'
    context_object_name = 'bom'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            from production.models import ProductionOrder
            ctx['bom_usage'] = ProductionOrder.objects.filter(bom=self.object) \
                .order_by('-created_at')[:10]
        except Exception:
            ctx['bom_usage'] = []
        return ctx

class BOMActivateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        bom = get_object_or_404(BOM, pk=pk)

        # Deactivate any other active BOM for the same product
        BOM.objects.filter(product=bom.product, is_active=True) \
            .exclude(pk=bom.pk).update(is_active=False, is_draft=True)

        bom.is_active = True
        bom.is_draft = False
        bom.save()

        messages.success(request, f'BOM {bom.bom_code} is now **active**.')

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        return redirect('bom-list')

# products/views.py

class BOMCostCalculationView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = request.POST
            total_cost = 0

            for key in data:
                if key.startswith('material_') and key.endswith('_quantity'):
                    idx = key.split('_')[1]
                    material_id = data.get(f'material_{idx}_id')
                    quantity = float(data.get(key, 0))
                    waste = float(data.get(f'material_{idx}_waste', 0))

                    try:
                        material = Product.objects.get(id=material_id)
                        unit_cost = float(material.cost_price or 0)
                        total_qty = quantity * (1 + waste / 100)
                        total_cost += total_qty * unit_cost
                    except (Product.DoesNotExist, ValueError):
                        continue

            return JsonResponse({'success': True, 'total_cost': round(total_cost, 2)})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
