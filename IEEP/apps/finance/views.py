# finance/views.py
from django.views.generic import ListView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .models import Transaction, CostCalculation, Invoice

@method_decorator(login_required, name='dispatch')
class TransactionListView(ListView):
    model = Transaction
    template_name = 'finance/transaction_list.html'
    context_object_name = 'transactions'
    ordering = ['-transaction_date']
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset()
        # Filter by search
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                models.Q(reference_number__icontains=search) |
                models.Q(description__icontains=search)
            )
        # Filter by type
        ttype = self.request.GET.get('transaction_type')
        if ttype:
            qs = qs.filter(transaction_type=ttype)
        return qs.prefetch_related('journal_entry')

@method_decorator(login_required, name='dispatch')
class CostCalculationListView(ListView):
    model = CostCalculation
    template_name = 'finance/cost_calculation_list.html'
    context_object_name = 'cost_calculations'
    ordering = ['-calculated_at']

@method_decorator(login_required, name='dispatch')
class InvoiceListView(ListView):
    model = Invoice
    template_name = 'finance/invoice_list.html'
    context_object_name = 'invoices'
    ordering = ['-invoice_date']