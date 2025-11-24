from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import uuid
import logging
from apps.notifications.tasks import create_low_stock_notification
from .models import StockItem, StockTransaction
from .services.procurement_integration import ProcurementIntegrationService
from apps.procurement.models import GoodsReceipt, PurchaseOrder
from apps.finance.models import JournalEntry, JournalEntryLine
from apps.finance.accounting import get_account


logger = logging.getLogger(__name__)

@receiver(post_save, sender=StockItem)
def low_stock_handler(sender, instance: StockItem, created, **kwargs):
    """Handle low stock notifications with better error handling"""
    if not created:  # Only check for existing items
        if instance.should_send_alert:
            try:
                create_low_stock_notification.delay(instance.id)
            except Exception as e:
                logger.error(f"Failed to send low stock alert: {e}")
                # Fallback to synchronous execution
                try:
                    create_low_stock_notification(instance.id)
                except Exception as sync_error:
                    logger.error(f"Sync notification also failed: {sync_error}")


@receiver(post_save, sender=StockTransaction)
def create_stock_journal_entry(sender, instance: StockTransaction, created, **kwargs):
    """
    When a StockTransaction is **created**, generate a balanced
    double-entry journal entry based on transaction_type.
    """
    if not created:
        return  

    stock_item = instance.stock_item
    product = stock_item.product
    unit_cost = stock_item.unit_cost or Decimal('0.00')
    amount = abs(instance.quantity) * unit_cost

    if amount == Decimal('0') or instance.quantity == 0:
        return

    ACCOUNT_MAP = {
        'in': {
            'debit': '1500',   
            'credit': '5000',  
        },
        'out': {
            'debit': '6000',  
            'credit': '1500', 
        },
        'adjustment': {
            'debit': '1500' if instance.quantity > 0 else '6000',
            'credit': '6000' if instance.quantity > 0 else '1500',
        },
        'quality': {
            'skip': True
        },
        'transfer': {
            'debit': '1500',   
            'credit': '1500',
        },
    }

    mapping = ACCOUNT_MAP.get(instance.transaction_type)
    if not mapping or mapping.get('skip'):
        return 

    try:
        debit_account = get_account(mapping['debit'])
        credit_account = get_account(mapping['credit'])
    except Exception as e:
        print(f"[JOURNAL] Account missing for {instance.transaction_type}: {e}")
        return

    with transaction.atomic():
        entry_number = f"JE-STK-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        je = JournalEntry.objects.create(
            transaction=None,  
            entry_number=entry_number,
            posted_by=instance.created_by,
            description=(
                f"{instance.get_transaction_type_display()} "
                f"{product.sku} (Batch: {stock_item.batch_number or '-'}) – "
                f"{instance.reference or 'System'}"
            )
        )

        JournalEntryLine.objects.create(
            journal_entry=je,
            account=debit_account,
            debit=amount,
            credit=0,
            description=f"{instance.transaction_type.upper()} {product.sku}"
        )

        JournalEntryLine.objects.create(
            journal_entry=je,
            account=credit_account,
            debit=0,
            credit=amount,
            description=f"{instance.transaction_type.upper()} {product.sku}"
        )

@receiver(post_save, sender=GoodsReceipt)
def update_stock_on_goods_receipt(sender, instance, created, **kwargs):
    """Update stock when goods receipt is created"""
    if created:
        ProcurementIntegrationService.process_goods_receipt(instance)

@receiver(post_save, sender=PurchaseOrder)
def update_procurement_status_on_po_change(sender, instance, **kwargs):
    """Update stock item procurement status when PO status changes"""
    ProcurementIntegrationService.update_procurement_status(instance)