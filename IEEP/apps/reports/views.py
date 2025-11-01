from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.http import HttpResponse
from django.db import models
from django.db.models import F, FloatField
import csv
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
from apps.inventory.models import StockTransaction, StockItem, Warehouse
from apps.production.models import ProductionOrder
from apps.maintenance.models import MaintenanceOrder, Asset
from apps.products.models import Product

@method_decorator(login_required, name='dispatch')
class DashboardView(TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_products'] = Product.objects.count()
        context['low_stock_items'] = StockItem.objects.filter(
            quantity__lte=models.F('reorder_threshold'),
            quantity__gt=0
        ).count()
        context['active_work_orders'] = ProductionOrder.objects.filter(
            status__in=['planned', 'in_progress']
        ).count()
        context['pending_maintenance'] = Asset.objects.filter(
            next_maintenance_date__isnull=False
        ).count()
        return context

@method_decorator(login_required, name='dispatch')
class LowStockReportView(TemplateView):
    template_name = 'reports/low_stock_report.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = StockItem.objects.select_related(
            'product__unit_of_measure', 'warehouse'
        ).annotate(
            reorder_level=F('reorder_threshold'),
            stock_deficit=F('reorder_threshold') - F('quantity')
        ).filter(
            quantity__lte=F('reorder_threshold'),
            quantity__gt=0
        ).order_by('stock_deficit')

        warehouse = self.request.GET.get('warehouse')
        if warehouse:
            queryset = queryset.filter(warehouse_id=warehouse)

        context['low_stock_items'] = queryset
        context['warehouses'] = Warehouse.objects.filter(is_active=True)
        context['total_low_stock'] = queryset.count()
        context['total_deficit'] = sum(item.stock_deficit for item in queryset)
        return context

    def get(self, request, *args, **kwargs):
        export_format = request.GET.get('format')
        if export_format == 'csv':
            return self.export_csv()
        if export_format == 'pdf':
            return self.export_pdf()
        return super().get(request, *args, **kwargs)

    def export_csv(self):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="low_stock_report.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'SKU', 'Product', 'Batch', 'Warehouse', 'Current Qty',
            'Reorder Level', 'Deficit', 'Unit'
        ])

        items = self.get_context_data()['low_stock_items']
        for item in items:
            writer.writerow([
                item.product.sku,
                item.product.name,
                item.batch_number or '-',
                item.warehouse.code,
                float(item.quantity),
                float(item.reorder_threshold),
                float(item.stock_deficit),
                item.product.unit_of_measure.symbol
            ])

        return response

    def export_pdf(self):
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="low_stock_report.pdf"'

        doc = SimpleDocTemplate(response, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph("Low Stock Report", styles['Title']))
        elements.append(Paragraph(f"Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        elements.append(Spacer(1, 12))

        data = [['SKU', 'Product', 'Batch', 'Warehouse', 'Qty', 'Reorder', 'Deficit', 'Unit']]
        items = self.get_context_data()['low_stock_items']
        for item in items:
            data.append([
                item.product.sku,
                item.product.name[:30],
                item.batch_number or '-',
                item.warehouse.code,
                f"{item.quantity:.2f}",
                f"{item.reorder_threshold:.2f}",
                f"{item.stock_deficit:.2f}",
                item.product.unit_of_measure.symbol
            ])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(table)

        doc.build(elements)
        return response
