# management/commands/sync_reorder_thresholds.py
from django.core.management.base import BaseCommand
from apps.inventory.models import StockItem
from decimal import Decimal

class Command(BaseCommand):
    help = "Copy product.reorder_threshold → stockitem.reorder_threshold (if 0)"

    def handle(self, *args, **kwargs):
        qs = StockItem.objects.filter(reorder_threshold=0)
        updated = 0
        for si in qs.select_related('product'):
            if si.product.reorder_threshold > 0:
                si.reorder_threshold = si.product.reorder_threshold
                si.save(update_fields=['reorder_threshold'])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} StockItems"))