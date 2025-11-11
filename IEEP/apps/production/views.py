from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.db.models import Q, Count, Sum, F
from django.contrib import messages
from django.http import JsonResponse
from django.views import View
from django.utils import timezone
from .models import WorkOrder, ProductionStep, ProductionLog, MaterialIssue, DowntimeLog, MaterialConsumption, ProductionOrder, ProductionOrderItem
from apps.maintenance.models import Asset
from apps.products.models import Product
from django.contrib.auth import get_user_model


@method_decorator(login_required, name="dispatch")
class WorkOrderListView(ListView):
    model = WorkOrder
    template_name = "production/work_order_list.html"
    context_object_name = "work_orders"
    paginate_by = 20
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by status
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # Filter by product
        product = self.request.GET.get("product")
        if product:
            queryset = queryset.filter(product_id=product)

        # Filter by date
        date = self.request.GET.get("date")
        if date:
            queryset = queryset.filter(scheduled_start__date=date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add summary counts
        context["total_orders"] = WorkOrder.objects.count()
        context["in_progress_count"] = WorkOrder.objects.filter(
            status="in_progress"
        ).count()
        context["completed_count"] = WorkOrder.objects.filter(
            status="completed"
        ).count()
        context["qc_pending_count"] = WorkOrder.objects.filter(
            status="qc_pending"
        ).count()
        context["planned_count"] = WorkOrder.objects.filter(status="planned").count()

        context["products"] = Product.objects.filter(is_active=True)

        return context


@method_decorator(login_required, name="dispatch")
class WorkOrderDetailView(DetailView):
    model = WorkOrder
    template_name = "production/work_order_detail.html"
    context_object_name = "work_order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        work_order = self.get_object()

        # Add production logs
        context["production_logs"] = work_order.production_logs.all().order_by(
            "-created_at"
        )[:10]

        return context


User = get_user_model()

class WorkOrderCreateView(LoginRequiredMixin, CreateView):
    model = WorkOrder
    template_name = "production/work_order_form.html"
    fields = [
        "product",
        "bom",
        "planned_quantity",
        "priority",
        "scheduled_start",
        "scheduled_end",
        "assigned_machine",
        "operator",
    ]
    success_url = reverse_lazy('work-order-list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Set querysets for foreign key fields
        form.fields['product'].queryset = Product.objects.filter(is_active=True)
        # Updated to use Asset model with operational status
        form.fields['assigned_machine'].queryset = Asset.objects.filter(
            status__in=['operational', 'idle'], 
            asset_type__in=['production_machine', 'mixer', 'filler', 'packaging']
        )
        form.fields['operator'].queryset = User.objects.filter(is_active=True)
        return form

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.order_number = self.generate_order_number()
        return super().form_valid(form)

    def generate_order_number(self):
        from datetime import datetime
        return f"WO-{datetime.now().strftime('%Y%m%d')}-{WorkOrder.objects.count() + 1:04d}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = Product.objects.filter(is_active=True)
        # Updated to Asset model
        context['machines'] = Asset.objects.filter(
            status__in=['operational', 'idle'],
            asset_type__in=['production_machine', 'mixer', 'filler', 'packaging']
        )
        context['operators'] = User.objects.filter(is_active=True, groups__name='Operators')
        return context

class WorkOrderUpdateView(LoginRequiredMixin, UpdateView):
    model = WorkOrder
    template_name = "production/work_order_form.html"
    fields = [
        "product",
        "bom",
        "planned_quantity",
        "actual_quantity",
        "status",
        "priority",
        "scheduled_start",
        "scheduled_end",
        "actual_start",
        "actual_end",
        "assigned_machine",
        "operator",
        "qc_passed",
        "qc_notes",
    ]
    success_url = reverse_lazy('work-order-list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Set querysets for foreign key fields
        form.fields['product'].queryset = Product.objects.filter(is_active=True)
        # Updated to Asset model
        form.fields['assigned_machine'].queryset = Asset.objects.filter(
            status__in=['operational', 'idle'],
            asset_type__in=['production_machine', 'mixer', 'filler', 'packaging']
        )
        form.fields['operator'].queryset = User.objects.filter(is_active=True)
        return form

    def form_valid(self, form):
        # Create production log for status changes
        if "status" in form.changed_data:
            ProductionLog.objects.create(
                work_order=self.object,
                action="status_change",
                notes=f"Status changed from {self.object.status} to {form.cleaned_data['status']}",
                created_by=self.request.user,
            )

        # Log completion
        if form.cleaned_data["status"] == "completed" and "status" in form.changed_data:
            ProductionLog.objects.create(
                work_order=self.object,
                action="complete",
                quantity_produced=form.cleaned_data.get("actual_quantity", 0),
                notes="Production completed successfully",
                created_by=self.request.user,
            )

        return super().form_valid(form)
    def get_success_url(self):
        return reverse_lazy("work-order-detail", kwargs={"pk": self.object.pk})


# API Views
@method_decorator(login_required, name="dispatch")
class WorkOrderAPIView(View):
    def get(self, request):
        try:
            work_orders = WorkOrder.objects.select_related(
                "assigned_operator", "created_by"
            )

            data = {
                "success": True,
                "count": work_orders.count(),
                "work_orders": [
                    {
                        "id": wo.id,
                        "order_number": wo.order_number,
                        "product_sku": wo.product_sku,
                        "product_name": wo.product_name,
                        "planned_quantity": float(wo.planned_quantity),
                        "actual_quantity": float(wo.actual_quantity),
                        "status": wo.status,
                        "priority": wo.priority,
                        "yield_percentage": float(wo.yield_percentage),
                        "scheduled_start": (
                            wo.scheduled_start.isoformat()
                            if wo.scheduled_start
                            else None
                        ),
                        "scheduled_end": (
                            wo.scheduled_end.isoformat() if wo.scheduled_end else None
                        ),
                        "assigned_machine": wo.assigned_machine,
                        "assigned_operator": (
                            wo.assigned_operator.get_full_name()
                            if wo.assigned_operator
                            else None
                        ),
                        "is_overdue": wo.is_overdue,
                        "created_at": wo.created_at.isoformat(),
                    }
                    for wo in work_orders
                ],
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


@method_decorator(login_required, name="dispatch")
class ProductionDashboardView(View):
    def get(self, request):
        try:
            # Production statistics
            total_orders = WorkOrder.objects.count()
            completed_orders = WorkOrder.objects.filter(status="completed").count()
            in_progress_orders = WorkOrder.objects.filter(status="in_progress").count()
            overdue_orders = WorkOrder.objects.filter(
                scheduled_end__lt=timezone.now(), status__in=["planned", "in_progress"]
            ).count()

            # Yield statistics
            total_planned = (
                WorkOrder.objects.filter(status="completed").aggregate(
                    total=Sum("planned_quantity")
                )["total"]
                or 0
            )
            total_actual = (
                WorkOrder.objects.filter(status="completed").aggregate(
                    total=Sum("actual_quantity")
                )["total"]
                or 0
            )
            overall_yield = (
                (total_actual / total_planned * 100) if total_planned > 0 else 0
            )

            # Recent activity
            recent_logs = ProductionLog.objects.select_related(
                "work_order", "created_by"
            ).order_by("-created_at")[:10]

            data = {
                "success": True,
                "dashboard": {
                    "total_orders": total_orders,
                    "completed_orders": completed_orders,
                    "in_progress_orders": in_progress_orders,
                    "overdue_orders": overdue_orders,
                    "overall_yield": float(overall_yield),
                    "total_planned": float(total_planned),
                    "total_actual": float(total_actual),
                },
                "recent_activity": [
                    {
                        "work_order": log.work_order.order_number,
                        "log_type": log.log_type,
                        "notes": log.notes,
                        "created_by": log.created_by.get_full_name()
                        or log.created_by.username,
                        "created_at": log.created_at.isoformat(),
                    }
                    for log in recent_logs
                ],
            }
            return JsonResponse(data)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


# Action Views
class StartProductionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        work_order = get_object_or_404(WorkOrder, pk=pk)

        if work_order.status == "planned":
            work_order.status = "in_progress"
            work_order.actual_start = timezone.now()
            work_order.save()

            # Create production log
            ProductionLog.objects.create(
                work_order=work_order,
                log_type="start",
                notes="Production started",
                created_by=request.user,
            )

            return JsonResponse(
                {"success": True, "message": "Production started successfully"}
            )

        return JsonResponse(
            {"success": False, "error": "Cannot start production for this order"}
        )


class CompleteProductionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        work_order = get_object_or_404(WorkOrder, pk=pk)

        if work_order.status == "in_progress":
            work_order.status = "completed"
            work_order.actual_end = timezone.now()
            work_order.save()

            # Create production log
            ProductionLog.objects.create(
                work_order=work_order,
                log_type="complete",
                quantity_produced=work_order.actual_quantity,
                notes="Production completed",
                created_by=request.user,
            )

            return JsonResponse(
                {"success": True, "message": "Production completed successfully"}
            )

        return JsonResponse(
            {"success": False, "error": "Cannot complete production for this order"}
        )


class AddProductionLogView(LoginRequiredMixin, View):
    def post(self, request, pk):
        work_order = get_object_or_404(WorkOrder, pk=pk)

        log_type = request.POST.get("log_type")
        quantity_produced = request.POST.get("quantity_produced", 0)
        notes = request.POST.get("notes", "")

        try:
            ProductionLog.objects.create(
                work_order=work_order,
                log_type=log_type,
                quantity_produced=quantity_produced,
                notes=notes,
                created_by=request.user,
            )

            # Update work order actual quantity if provided
            if quantity_produced and float(quantity_produced) > 0:
                work_order.actual_quantity = float(quantity_produced)
                work_order.save()

            return JsonResponse(
                {"success": True, "message": "Production log added successfully"}
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})


@method_decorator(login_required, name="dispatch")
class ProductionBoardView(ListView):
    template_name = "production/production_board.html"
    context_object_name = "work_orders"

    def get_queryset(self):
        return WorkOrder.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Group work orders by status
        context["planned_orders"] = WorkOrder.objects.filter(status="planned").order_by(
            "scheduled_start"
        )
        context["in_progress_orders"] = WorkOrder.objects.filter(
            status="in_progress"
        ).order_by("-actual_start")
        context["qc_pending_orders"] = WorkOrder.objects.filter(
            status="qc_pending"
        ).order_by("-actual_end")
        context["completed_orders"] = WorkOrder.objects.filter(
            status="completed"
        ).order_by("-actual_end")[:10]

        # Add summary counts
        from django.utils import timezone

        today = timezone.now().date()
        context["completed_today_count"] = WorkOrder.objects.filter(
            status="completed", actual_end__date=today
        ).count()

        context["behind_schedule_count"] = WorkOrder.objects.filter(
            Q(status="planned") | Q(status="in_progress"),
            scheduled_end__lt=timezone.now(),
        ).count()

        # Updated to Asset model - show production machines
        context["machines"] = Asset.objects.filter(
            asset_type__in=['production_machine', 'mixer', 'filler', 'packaging']
        )

        return context

class WorkOrderReportView(LoginRequiredMixin, DetailView):
    model = WorkOrder
    template_name = 'production/work_order_report.html'
    context_object_name = 'work_order'  # This makes the object available as 'work_order'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any additional context you need
        return context

class MaterialIssueCreateView(LoginRequiredMixin, CreateView):
    model = MaterialIssue
    fields = ['product', 'quantity', 'batch_number', 'notes']
    template_name = 'production/material_issue_form.html'
    
    def get_success_url(self):
        work_order_id = self.request.GET.get('work_order')
        if work_order_id:
            return reverse('work-order-detail', kwargs={'pk': work_order_id})
        return reverse('work-order-list')
    
    def get_initial(self):
        initial = super().get_initial()
        work_order_id = self.request.GET.get('work_order')
        if work_order_id:
            work_order = get_object_or_404(WorkOrder, pk=work_order_id)
            initial['work_order'] = work_order
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        work_order_id = self.request.GET.get('work_order')
        if work_order_id:
            context['work_order'] = get_object_or_404(WorkOrder, pk=work_order_id)
        return context
    
    def form_valid(self, form):
        work_order_id = self.request.GET.get('work_order')
        if work_order_id:
            form.instance.work_order = get_object_or_404(WorkOrder, pk=work_order_id)
        form.instance.issued_by = self.request.user
        messages.success(self.request, 'Material issued successfully.')
        return super().form_valid(form)


class DowntimeCreateView(LoginRequiredMixin, CreateView):
    model = DowntimeLog
    fields = ['machine', 'downtime_type', 'start_time', 'end_time', 'reason']
    template_name = 'production/downtime_form.html'
    
    def get_success_url(self):
        work_order_id = self.request.GET.get('work_order')
        if work_order_id:
            return reverse('work-order-detail', kwargs={'pk': work_order_id})
        return reverse('work-order-list')
    
    def get_initial(self):
        initial = super().get_initial()
        work_order_id = self.request.GET.get('work_order')
        if work_order_id:
            work_order = get_object_or_404(WorkOrder, pk=work_order_id)
            initial['work_order'] = work_order
            initial['machine'] = work_order.assigned_machine
            initial['start_time'] = timezone.now()
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        work_order_id = self.request.GET.get('work_order')
        if work_order_id:
            context['work_order'] = get_object_or_404(WorkOrder, pk=work_order_id)
        return context
    
    def form_valid(self, form):
        work_order_id = self.request.GET.get('work_order')
        if work_order_id:
            form.instance.work_order = get_object_or_404(WorkOrder, pk=work_order_id)
        messages.success(self.request, 'Downtime logged successfully.')
        return super().form_valid(form)

# Add this to production/views.py after the other views

class QualityCheckCreateView(LoginRequiredMixin, View):
    template_name = 'production/quality_check_form.html'
    
    def get(self, request, *args, **kwargs):
        work_order_id = request.GET.get('work_order')
        if not work_order_id:
            messages.error(request, 'Work order ID is required.')
            return redirect('work-order-list')
            
        work_order = get_object_or_404(WorkOrder, pk=work_order_id)
        
        # Simple form for QC update
        return render(request, self.template_name, {'work_order': work_order})
    
    def post(self, request, *args, **kwargs):
        work_order_id = request.GET.get('work_order')
        if not work_order_id:
            messages.error(request, 'Work order ID is required.')
            return redirect('work-order-list')
            
        work_order = get_object_or_404(WorkOrder, pk=work_order_id)
        
        qc_passed = request.POST.get('qc_passed') == 'true'
        qc_notes = request.POST.get('qc_notes', '')
        
        work_order.qc_passed = qc_passed
        work_order.qc_notes = qc_notes
        work_order.status = 'completed' if qc_passed else 'qc_pending'
        work_order.save()
        
        # Create production log
        ProductionLog.objects.create(
            work_order=work_order,
            action='qc_check',
            notes=f"QC {'PASSED' if qc_passed else 'FAILED'}: {qc_notes}",
            created_by=request.user,
        )
        
        messages.success(request, f"QC {'passed' if qc_passed else 'failed'} recorded successfully.")
        return redirect('work-order-detail', pk=work_order_id)
