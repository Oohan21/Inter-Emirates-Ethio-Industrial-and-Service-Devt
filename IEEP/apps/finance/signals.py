# finance/signals.py   (new file)
import uuid
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Transaction, JournalEntry, JournalEntryLine
from .accounting import get_account

@receiver(post_save, sender=Transaction)
def create_journal_entry(sender, instance: Transaction, created, **kwargs):
    """
    When a Transaction is **created** (not updated), generate a balanced
    double-entry journal entry based on `transaction_type`.
    """
    if not created:
        return  # we only post on creation

    # ------------------------------------------------------------------
    # 1. Determine the two accounts for the transaction type
    # ------------------------------------------------------------------
    ACCOUNT_MAP = {
        'purchase': {
            'debit': 'INV001',   # Inventory (Asset)
            'credit': 'AP001',   # Accounts Payable (Liability)
        },
        'sale': {
            'debit': 'AR001',    # Accounts Receivable (Asset)
            'credit': 'REV001',  # Sales Revenue (Revenue)
        },
        'production': {
            'debit': 'WIP001',   # Work-in-Progress (Asset)
            'credit': 'COGS001', # Cost of Goods Sold (Expense)
        },
        'maintenance': {
            'debit': 'MNT001',   # Maintenance Expense
            'credit': 'AP001',   # Accounts Payable
        },
        'adjustment': {
            'debit': 'ADJ001',   # Adjustment (Expense/Asset)
            'credit': 'ADJ001',  # same account – net zero
        },
        'transfer': {
            'debit': 'CASH001',  # Cash (Asset)
            'credit': 'CASH001', # same account – net zero
        },
    }

    mapping = ACCOUNT_MAP.get(instance.transaction_type)
    if not mapping:
        # Unknown type – skip posting (or raise error)
        return

    try:
        debit_account = get_account(mapping['debit'])
        credit_account = get_account(mapping['credit'])
    except Exception as exc:
        # In production you would log this, not raise
        print(f"[JOURNAL] Account missing for {instance.transaction_type}: {exc}")
        return

    # ------------------------------------------------------------------
    # 2. Create the JournalEntry header
    # ------------------------------------------------------------------
    entry_number = f"JE-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    journal = JournalEntry.objects.create(
        transaction=instance,
        entry_number=entry_number,
        posted_by=instance.created_by,
        description=instance.description or f"{instance.get_transaction_type_display()} – {instance.reference_number}"
    )

    # ------------------------------------------------------------------
    # 3. Create the two lines (balanced)
    # ------------------------------------------------------------------
    amount = instance.amount

    # Debit line
    JournalEntryLine.objects.create(
        journal_entry=journal,
        account=debit_account,
        debit=amount,
        credit=0,
        description=f"Debit {debit_account.name}"
    )

    # Credit line
    JournalEntryLine.objects.create(
        journal_entry=journal,
        account=credit_account,
        debit=0,
        credit=amount,
        description=f"Credit {credit_account.name}"
    )