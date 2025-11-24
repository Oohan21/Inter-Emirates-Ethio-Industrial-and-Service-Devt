# inventory/services/finance_integration.py
from django.utils import timezone
from apps.finance.models import Transaction, JournalEntry, JournalEntryLine, Account
from apps.finance.accounting import get_account
import uuid

class FinanceIntegrationService:
    @staticmethod
    def create_stock_adjustment_entry(stock_transaction, adjustment_amount, unit_cost):
        """
        Create finance entries for stock adjustments
        """
        try:
            # Generate unique reference
            ref_number = f"STK-ADJ-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            
            # Calculate total value change
            total_value_change = abs(adjustment_amount * unit_cost)
            
            # Create the transaction
            transaction = Transaction.objects.create(
                reference_number=ref_number,
                transaction_type='adjustment',
                description=f"Stock adjustment: {stock_transaction.stock_item.product.sku} - {stock_transaction.reference}",
                amount=total_value_change,
                transaction_date=timezone.now(),
                related_document=f"StockTransaction-{stock_transaction.id}",
                created_by=stock_transaction.created_by
            )
            
            # Create journal entry
            journal_entry = JournalEntry.objects.create(
                transaction=transaction,
                entry_number=ref_number,
                posted_by=stock_transaction.created_by,
                description=f"Stock adjustment for {stock_transaction.stock_item.product.sku}"
            )
            
            # Create journal entry lines based on adjustment type
            if adjustment_amount > 0:  # Stock increase
                # Debit Inventory Asset, Credit Adjustment Expense (reversal)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=get_account('1100'),  # Inventory Asset
                    debit=total_value_change,
                    credit=0,
                    description=f"Increase in {stock_transaction.stock_item.product.sku}"
                )
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=get_account('6100'),  # Inventory Adjustment Expense
                    debit=0,
                    credit=total_value_change,
                    description=f"Adjustment reversal for {stock_transaction.stock_item.product.sku}"
                )
            else:  # Stock decrease
                # Debit Adjustment Expense, Credit Inventory Asset
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=get_account('6100'),  # Inventory Adjustment Expense
                    debit=total_value_change,
                    credit=0,
                    description=f"Stock loss for {stock_transaction.stock_item.product.sku}"
                )
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=get_account('1100'),  # Inventory Asset
                    debit=0,
                    credit=total_value_change,
                    description=f"Decrease in {stock_transaction.stock_item.product.sku}"
                )
            
            return journal_entry
            
        except Exception as e:
            print(f"Finance integration error: {e}")
            return None

    @staticmethod
    def create_sale_entry(sale_order):
        """Create financial transaction for sales"""
        try:
            transaction = Transaction.objects.create(
                reference_number=sale_order.order_number,
                transaction_type='sale',
                amount=sale_order.grand_total,
                transaction_date=timezone.now(),
                description=f"Sale to {sale_order.customer.name}",
                related_document='sale_order',
                related_document_id=sale_order.id,
                created_by=sale_order.created_by
            )
            return transaction
        except Exception as e:
            logger.error(f"Sales finance entry failed: {e}")
            return None