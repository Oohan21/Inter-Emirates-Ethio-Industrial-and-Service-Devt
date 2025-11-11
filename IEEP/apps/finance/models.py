# finance/models.py
from django.db import models

class Account(models.Model):
    ACCOUNT_TYPES = [
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('revenue', 'Revenue'),
        ('expense', 'Expense'),
        ('cost_of_goods_sold', 'Cost of Goods Sold'),
    ]
    
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['account_type']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('purchase', 'Purchase'),
        ('sale', 'Sale'),
        ('production', 'Production Cost'),
        ('maintenance', 'Maintenance Cost'),
        ('adjustment', 'Inventory Adjustment'),
        ('transfer', 'Transfer'),
    ]
    
    reference_number = models.CharField(max_length=100, unique=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_date = models.DateTimeField()
    related_document = models.CharField(max_length=100, blank=True)
    related_document_id = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['reference_number']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['transaction_date']),
        ]

    def __str__(self):
        return f"{self.reference_number} - {self.transaction_type}"

class TransactionLine(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.transaction} - {self.account.code}"

class CostCalculation(models.Model):
    production_order = models.OneToOneField('production.ProductionOrder', on_delete=models.CASCADE)
    material_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overhead_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_per_unit = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    calculated_at = models.DateTimeField(auto_now_add=True)
    calculated_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.production_order} - Cost Calculation"

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    
    invoice_number = models.CharField(max_length=50, unique=True)
    supplier = models.ForeignKey('procurement.Supplier', on_delete=models.PROTECT)
    purchase_order = models.ForeignKey('procurement.PurchaseOrder', on_delete=models.PROTECT)
    invoice_date = models.DateField()
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
        ]

    def __str__(self):
        return self.invoice_number

class JournalEntry(models.Model):
    """
    Header for a double-entry journal entry.
    One Transaction → one JournalEntry (1-to-1).
    """
    transaction = models.OneToOneField(
        Transaction,
        on_delete=models.PROTECT,
        related_name='journal_entry'
    )
    entry_number = models.CharField(max_length=30, unique=True, editable=False)
    posted_at = models.DateTimeField(auto_now_add=True)
    posted_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    description = models.TextField(blank=True)

    def __str__(self):
        return self.entry_number

    class Meta:
        indexes = [
            models.Index(fields=['entry_number']),
            models.Index(fields=['posted_at']),
        ]


class JournalEntryLine(models.Model):
    """
    Debit / Credit line belonging to a JournalEntry.
    """
    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.CASCADE, related_name='lines'
    )
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.account.code} – D:{self.debit} C:{self.credit}"

    class Meta:
        indexes = [
            models.Index(fields=['journal_entry']),
            models.Index(fields=['account']),
        ]