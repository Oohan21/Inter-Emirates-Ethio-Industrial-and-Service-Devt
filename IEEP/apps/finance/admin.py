# finance/admin.py
from django.contrib import admin
from .models import Account, Transaction, TransactionLine, CostCalculation, Invoice, JournalEntry, JournalEntryLine

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'account_type', 'is_active']
    list_filter = ['account_type', 'is_active']
    search_fields = ['code', 'name']

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['reference_number', 'transaction_type', 'amount', 'transaction_date']
    list_filter = ['transaction_type']
    search_fields = ['reference_number']
    readonly_fields = ['created_at']

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'supplier', 'status', 'invoice_date', 'due_date', 'total_amount']
    list_filter = ['status']
    search_fields = ['invoice_number']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(CostCalculation)
class CostCalculationAdmin(admin.ModelAdmin):
    list_display = ['production_order', 'total_cost', 'cost_per_unit', 'calculated_at']
    readonly_fields = ['calculated_at']

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ['entry_number', 'transaction', 'posted_at', 'posted_by']
    list_filter = ['posted_at']
    search_fields = ['entry_number', 'transaction__reference_number']
    readonly_fields = ['entry_number', 'posted_at', 'posted_by']

@admin.register(JournalEntryLine)
class JournalEntryLineAdmin(admin.ModelAdmin):
    list_display = ['journal_entry', 'account', 'debit', 'credit']
    list_filter = ['account__account_type']
    search_fields = ['journal_entry__entry_number']