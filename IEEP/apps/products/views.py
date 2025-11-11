from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View, DeleteView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Avg, Count, F
from django.core.paginator import Paginator
from django.utils import timezone
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
import csv
from decimal import Decimal
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from .models import Product, Category, BOM, BOMComponent, ProductImage
from .forms import ProductForm, BOMForm, BOMComponentForm, ProductImageForm
from apps.production.models import ProductionOrder, ProductionOrderItem
from apps.production.forms import ProductionOrderForm, ProductionOrderItemFormSet
from apps.inventory.models import StockTransaction
from apps.inventory.forms import StockAdjustmentForm, StockItem


@method_decorator(login_required, name="dispatch")
class ProductListView(ListView):
    model = Product
    template_name = "products/product_list.html"
    context_object_name = "products"
    paginate_by = 20
    ordering = ["sku"]

    def get_queryset(self):
        queryset = super().get_queryset()

        product_type = self.request.GET.get("product_type")
        if product_type:
            queryset = queryset.filter(product_type=product_type)

        category = self.request.GET.get("category")
        if category:
            queryset = queryset.filter(category__name=category)

        status = self.request.GET.get("status")
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)

        return queryset


@method_decorator(login_required, name="dispatch")
class ProductDetailView(DetailView):
    model = Product
    template_name = "products/product_detail.html"
    context_object_name = "product"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()

        try:
            from inventory.models import StockItem

            stock_items = StockItem.objects.filter(product=product)
            context["total_stock"] = sum(item.quantity for item in stock_items)
            context["warehouse_count"] = (
                stock_items.values("warehouse").distinct().count()
            )
            if stock_items.exists():
                context["last_stock_update"] = (
                    stock_items.order_by("-updated_at").first().updated_at
                )
            else:
                context["last_stock_update"] = None
        except:
            context["total_stock"] = 0
            context["warehouse_count"] = 0
            context["last_stock_update"] = None

        try:
            from production.models import ProductionOrder

            work_orders = ProductionOrder.objects.filter(product=product)
            context["work_order_count"] = work_orders.count()
            avg_yield = work_orders.aggregate(Avg("actual_yield"))["actual_yield__avg"]
            context["average_yield"] = avg_yield or 0
            if work_orders.exists():
                context["last_production"] = (
                    work_orders.order_by("-created_at").first().created_at
                )
            else:
                context["last_production"] = None
        except:
            context["work_order_count"] = 0
            context["average_yield"] = 0
            context["last_production"] = None

        return context

@method_decorator(login_required, name="dispatch")
class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('product-list')
    success_message = "Product created successfully."

    def form_valid(self, form):
        self.object = form.save()
        self.handle_images()
        messages.success(self.request, self.success_message)
        return HttpResponseRedirect(self.get_success_url())

    def handle_images(self):
        product = self.object
        files = self.request.FILES.getlist('new_images')
        removed = self.request.POST.getlist('remove_images')
        ProductImage.objects.filter(id__in=removed, product=product).delete()

        for i, file in enumerate(files):
            is_main = (i == 0 and not product.images.filter(is_main=True).exists())
            ProductImage.objects.create(product=product, image=file, is_main=is_main)

        main_image_id = self.request.POST.get('set_main_image')
        if main_image_id:
            ProductImage.objects.filter(product=product, is_main=True).update(is_main=False)
            ProductImage.objects.filter(id=main_image_id, product=product).update(is_main=True)
        
        if not product.images.filter(is_main=True).exists() and product.images.exists():
            first_image = product.images.first()
            first_image.is_main = True
            first_image.save()

@method_decorator(login_required, name="dispatch")
class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'products/product_form.html'
    success_url = reverse_lazy('product-list')
    success_message = "Product updated successfully."

    def form_valid(self, form):
        response = super().form_valid(form)
        self.handle_images()
        return response

    def handle_images(self):
        product = self.object
        files = self.request.FILES.getlist('new_images')
        for i, file in enumerate(files):
            is_main = (i == 0 and not product.images.filter(is_main=True).exists())
            ProductImage.objects.create(product=product, image=file, is_main=is_main)
        
        removed_ids = self.request.POST.getlist('remove_images')
        ProductImage.objects.filter(id__in=removed_ids, product=product).delete()
        
        main_image_id = self.request.POST.get('set_main_image')
        if main_image_id:
            ProductImage.objects.filter(product=product, is_main=True).update(is_main=False)
            ProductImage.objects.filter(id=main_image_id, product=product).update(is_main=True)
        
        if not product.images.filter(is_main=True).exists() and product.images.exists():
            first_image = product.images.first()
            first_image.is_main = True
            first_image.save()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'].instance.images.set(self.object.images.all())
        return context

@method_decorator(login_required, name="dispatch")
class CategoryListView(ListView):
    model = Category
    template_name = "products/category_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories_with_counts = []
        for category in context["categories"]:
            categories_with_counts.append(
                {
                    "category": category,
                    "finished_goods_count": category.finished_goods_count,
                    "raw_materials_count": category.raw_materials_count,
                    "intermediate_count": category.intermediate_count,
                }
            )
        context["categories_with_counts"] = categories_with_counts
        return context


@method_decorator(login_required, name="dispatch")
class BOMListView(LoginRequiredMixin, ListView):
    model = BOM
    template_name = "products/bom_list.html"
    context_object_name = "boms"
    paginate_by = 20
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("product", "created_by")
        # Filters
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(is_active=(status == "active"))

        product_id = self.request.GET.get("product")
        if product_id:
            qs = qs.filter(product_id=product_id)

        search = self.request.GET.get("search")
        if search:
            qs = qs.filter(
                Q(bom_code__icontains=search)
                | Q(product__sku__icontains=search)
                | Q(product__name__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["products"] = Product.objects.filter(
            is_active=True, product_type="finished"
        )
        ctx["current_filters"] = self.request.GET.urlencode()
        return ctx

@method_decorator(login_required, name="dispatch")
class BOMCreateView(LoginRequiredMixin, CreateView):
    model = BOM
    form_class = BOMForm
    template_name = "products/bom_form.html"
    success_url = reverse_lazy("bom-list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["components"] = BOMComponentFormSet(self.request.POST)
        else:
            ctx["components"] = BOMComponentFormSet()
        return ctx

    def form_valid(self, form):
        context = self.get_context_data()
        components = context["components"]

        with transaction.atomic():
            form.instance.created_by = self.request.user
            form.instance.is_draft = True
            self.object = form.save()

            if components.is_valid():
                components.instance = self.object
                components.save()
                messages.success(
                    self.request, f"BOM {self.object.bom_code} created (draft)."
                )
            else:
                # Add formset errors to messages
                for error in components.errors:
                    messages.error(self.request, f"Component error: {error}")
                return self.form_invalid(form)

        return super().form_valid(form)

@method_decorator(login_required, name="dispatch")
class BOMPreviewView(LoginRequiredMixin, DetailView):
    model = BOM
    template_name = 'products/bom_detail.html'
    context_object_name = 'bom'

    def get_queryset(self):
        return super().get_queryset().select_related('product').prefetch_related('components__component')


class BOMActivateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        bom = get_object_or_404(BOM, pk=pk)

        # Deactivate any other active BOM for the same product
        BOM.objects.filter(product=bom.product, is_active=True).exclude(
            pk=bom.pk
        ).update(is_active=False, is_draft=True)

        bom.is_active = True
        bom.is_draft = False
        bom.save()

        messages.success(request, f"BOM {bom.bom_code} is now **active**.")

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        return redirect("bom-list")

class BOMCostCalculationView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = request.POST
            total_cost = 0

            for key in data:
                if key.startswith("material_") and key.endswith("_quantity"):
                    idx = key.split("_")[1]
                    material_id = data.get(f"material_{idx}_id")
                    quantity = float(data.get(key, 0))
                    waste = float(data.get(f"material_{idx}_waste", 0))

                    try:
                        material = Product.objects.get(id=material_id)
                        unit_cost = float(material.cost_price or 0)
                        total_qty = quantity * (1 + waste / 100)
                        total_cost += total_qty * unit_cost
                    except (Product.DoesNotExist, ValueError):
                        continue

            return JsonResponse({"success": True, "total_cost": round(total_cost, 2)})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})


class ProductTransactionListView(LoginRequiredMixin, ListView):
    model = StockTransaction
    template_name = "products/product_transactions.html"
    context_object_name = "transactions"
    paginate_by = 25

    def get_queryset(self):
        product = get_object_or_404(Product, pk=self.kwargs["pk"])
        return (
            StockTransaction.objects.filter(stock_item__product=product)
            .select_related("stock_item__warehouse", "created_by")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["product"] = get_object_or_404(Product, pk=self.kwargs["pk"])
        return context

class CreateWorkOrderFromProductView(LoginRequiredMixin, CreateView):
    model = ProductionOrder
    form_class = ProductionOrderForm
    template_name = "production/production_order_form.html"

    def get(self, request, pk):
        bom = get_object_or_404(BOM, pk=pk)
        return redirect(reverse('create-work-order-from-product', kwargs={'pk': bom.product.pk}))

    def get_initial(self):
        product = get_object_or_404(Product, pk=self.kwargs["pk"])
        return {
            "product": product,
            "planned_quantity": 1,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = get_object_or_404(Product, pk=self.kwargs["pk"])
        context["product"] = product
        context["bom"] = BOM.objects.filter(product=product, is_active=True).first()

        if self.request.POST:
            context["items"] = ProductionOrderItemFormSet(
            self.request.POST, instance=self.object
        )
        else:
            formset = ProductionOrderItemFormSet(instance=self.object)

            if context["bom"] and not self.object.pk:
                initial = []
                for comp in context["bom"].components.all():
                    initial.append(
                    {
                        "product": comp.component,
                        "planned_quantity": comp.effective_quantity,
                        "unit_of_measure": comp.component.unit_of_measure.symbol,
                    }
                )
                formset = ProductionOrderItemFormSet(instance=self.object, initial=initial)
            context["items"] = formset
        return context


    def form_valid(self, form):
        context = self.get_context_data()
        items = context["items"]

        with transaction.atomic():
            self.object = form.save()
            if items.is_valid():
              items.instance = self.object
              items.save()
            else:
                return self.form_invalid(form)

        messages.success(self.request, f"Work order {self.object.order_number} created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("production-order-detail", kwargs={"pk": self.object.pk})

class ProductDeactivateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        product.is_active = False
        product.save()
        messages.success(request, f"Product {product.sku} deactivated.")
        return redirect('product-detail', pk=pk)

class BOMUpdateView(LoginRequiredMixin, UpdateView):
    model = BOM
    form_class = BOMForm
    template_name = 'products/bom_form.html'
    context_object_name = 'bom'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit BOM: {self.object.bom_code}"
        if self.request.POST:
            context['components'] = BOMComponentForm(self.request.POST, instance=self.object)
        else:
            context['components'] = BOMComponentForm(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        components = context['components']
        with transaction.atomic():
            self.object = form.save()
            if components.is_valid():
                components.instance = self.object
                components.save()
            else:
                return self.form_invalid(form)
        messages.success(self.request, f"BOM {self.object.bom_code} updated.")
        return redirect('bom-detail', pk=self.object.pk)


class BOMNewVersionView(LoginRequiredMixin, CreateView):
    model = BOM
    form_class = BOMForm
    template_name = 'products/bom_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.old_bom = get_object_or_404(BOM, pk=kwargs['pk'])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {
            'product': self.old_bom.product,
            'version': self.old_bom.version + 1,
            'labor_cost': self.old_bom.labor_cost,
            'overhead_cost': self.old_bom.overhead_cost,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"New Version of {self.old_bom.bom_code}"
        if self.request.POST:
            context['components'] = BOMComponentForm(self.request.POST)
        else:
            formset = BOMComponentForm()
            initial = []
            for comp in self.old_bom.components.all():
                initial.append({
                    'component': comp.component,
                    'quantity': comp.quantity,
                    'waste_percentage': comp.waste_percentage,
                    'unit_cost': comp.unit_cost,
                })
            formset = BOMComponentForm(initial=initial)
            context['components'] = formset
        return context

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
        messages.success(self.request, f"New version {self.object.bom_code} created as draft.")
        return redirect('bom-detail', pk=self.object.pk)

class BOMExportView(DetailView):
    model = BOM

    def get(self, request, *args, **kwargs):
        bom = self.get_object()
        format = request.GET.get('format', 'xlsx')

        if format == 'pdf':
            return self.export_pdf(bom)
        else:
            return self.export_excel(bom)

    def export_excel(self, bom):
        wb = Workbook()
        ws = wb.active
        ws.title = f"BOM {bom.bom_code}"

        headers = ['SKU', 'Name', 'Qty', 'Waste %', 'UOM', 'Unit Cost', 'Total Cost']
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')

        for comp in bom.components.all():
            ws.append([
                comp.component.sku,
                comp.component.name,
                f"{comp.quantity:.4f}",
                f"{comp.waste_percentage:.1f}",
                comp.component.unit_of_measure.symbol,
                f"{comp.unit_cost:.2f}",
                f"{comp.total_cost:.2f}"
            ])

        ws.append([])
        ws.append(['', '', '', '', 'Labor Cost', f"{bom.labor_cost:.2f}"])
        ws.append(['', '', '', '', 'Overhead Cost', f"{bom.overhead_cost:.2f}"])
        ws.append(['', '', '', '', 'Total Cost', f"{bom.total_cost:.2f}"])

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="BOM_{bom.bom_code}.xlsx"'
        wb.save(response)
        return response

    def export_pdf(self, bom):
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph(f"BOM: {bom.bom_code} - v{bom.version}", styles['Title']))
        elements.append(Spacer(1, 12))

        data = [['SKU', 'Name', 'Qty', 'Waste', 'UOM', 'Cost', 'Total']]
        for comp in bom.components.all():
            data.append([
                comp.component.sku,
                comp.component.name,
                f"{comp.quantity:.4f}",
                f"{comp.waste_percentage:.1f}%",
                comp.component.unit_of_measure.symbol,
                f"{comp.unit_cost:.2f}",
                f"{comp.total_cost:.2f}"
            ])
        data.append(['', '', '', '', 'Labor', '', f"{bom.labor_cost:.2f}"])
        data.append(['', '', '', '', 'Overhead', '', f"{bom.overhead_cost:.2f}"])
        data.append(['', '', '', '', 'TOTAL', '', f"{bom.total_cost:.2f}"])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]))
        elements.append(table)
        doc.build(elements)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="BOM_{bom.bom_code}.pdf"'
        return response

class BOMPickListView(DetailView):
    model = BOM
    template_name = 'products/pick_list.html'

    def get(self, request, *args, **kwargs):
        bom = self.get_object()
        quantity = request.GET.get('quantity', '1')
        
        try:
            # Convert to Decimal to avoid float precision issues
            production_qty = Decimal(quantity)
        except (ValueError, TypeError):
            production_qty = Decimal('1')

        pick_list = []
        total_shortage = Decimal('0')
        fully_available = 0
        partial_stock = 0
        out_of_stock = 0

        for comp in bom.components.select_related('component').all():
            required = comp.quantity * production_qty  # Now Decimal * Decimal = OK
            available = sum(
                item.quantity for item in 
                comp.component.stock_items.filter(warehouse__is_active=True)
            )
            shortage = max(required - available, Decimal('0'))

            if shortage == 0:
                fully_available += 1
            elif available > 0:
                partial_stock += 1
            else:
                out_of_stock += 1

            total_shortage += shortage

            pick_list.append({
                'component': comp.component,
                'required': required,
                'available': available,
                'shortage': shortage,
                'uom': comp.component.unit_of_measure,
            })

        context = {
            'bom': bom,
            'production_quantity': production_qty,
            'pick_list': pick_list,
            'total_shortage': total_shortage,
            'fully_available_count': fully_available,
            'partial_stock_count': partial_stock,
            'out_of_stock_count': out_of_stock,
        }

        return render(request, self.template_name, context)

class BOMCostAnalysisView(DetailView):
    model = BOM

    def get(self, request, *args, **kwargs):
        bom = self.get_object()
        material_cost = bom.total_material_cost
        labor = bom.labor_cost
        overhead = bom.overhead_cost
        total = bom.total_cost

        return JsonResponse({
            'success': True,
            'data': {
                'material': float(material_cost),
                'labor': float(labor),
                'overhead': float(overhead),
                'total': float(total),
                'components': [
                    {
                        'sku': comp.component.sku,
                        'name': comp.component.name,
                        'cost': float(comp.total_cost)
                    } for comp in bom.components.all()
                ]
            }
        })


# ------------------------------------------------------------------
# 3. Compare Versions (List of BOMs for same product)
# ------------------------------------------------------------------
class BOMCompareView(ListView):
    model = BOM
    template_name = 'products/bom_compare.html'
    context_object_name = 'boms'

    def get_queryset(self):
        product_id = self.request.GET.get('product')
        if product_id:
            return BOM.objects.filter(product_id=product_id).order_by('-version')
        return BOM.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = Product.objects.filter(product_type='finished')
        context['selected_product'] = self.request.GET.get('product')
        return context

@method_decorator(login_required, name="dispatch")
class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product
    template_name = 'products/product_confirm_delete.html'
    success_url = reverse_lazy('product-list')
    success_message = "Product deleted successfully."

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        return super().delete(request, *args, **kwargs)

@method_decorator(login_required, name="dispatch")
class BOMDeleteView(LoginRequiredMixin, DeleteView):
    model = BOM
    template_name = 'products/bom_confirm_delete.html'
    success_url = reverse_lazy('bom-list')
    success_message = "BOM deleted successfully."

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        return super().delete(request, *args, **kwargs)
