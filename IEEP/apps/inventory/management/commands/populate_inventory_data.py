# inventory/management/commands/populate_inventory_data.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.inventory.models import Warehouse, StockItem
from apps.products.models import Product, UnitOfMeasure
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.db.models import signals

User = get_user_model()

class Command(BaseCommand):
    help = 'Populate inventory module with sample data'

    def handle(self, *args, **options):
        self.stdout.write('Creating sample inventory data...')
        
        # Disable signals during population to avoid Celery issues
        from apps.inventory import signals as inventory_signals
        from django.db.models.signals import post_save
        
        # Disconnect the signal that causes Celery tasks
        post_save.disconnect(inventory_signals.low_stock_handler, sender=StockItem)
        
        try:
            self._create_data()
        finally:
            # Reconnect the signal
            post_save.connect(inventory_signals.low_stock_handler, sender=StockItem)
    
    def _create_data(self):
        # Get or create user
        user, _ = User.objects.get_or_create(
            username='inventory_clerk',
            defaults={
                'email': 'inventory@factory.com',
                'first_name': 'Inventory',
                'last_name': 'Clerk'
            }
        )
        
        # Create warehouses
        warehouses_data = [
            {'code': 'WH-MAIN', 'name': 'Main Warehouse', 'location': 'Building A'},
            {'code': 'WH-RAW', 'name': 'Raw Materials Warehouse', 'location': 'Building B'},
            {'code': 'WH-FIN', 'name': 'Finished Goods Warehouse', 'location': 'Building C'},
        ]
        
        for wh_data in warehouses_data:
            warehouse, created = Warehouse.objects.get_or_create(
                code=wh_data['code'],
                defaults=wh_data
            )
            if created:
                self.stdout.write(f'Created warehouse: {warehouse.name}')
        
        # Get or create unit of measures
        kg_unit, _ = UnitOfMeasure.objects.get_or_create(
            name='Kilogram',
            defaults={'symbol': 'kg', 'conversion_factor': 1}
        )
        liter_unit, _ = UnitOfMeasure.objects.get_or_create(
            name='Liter',
            defaults={'symbol': 'L', 'conversion_factor': 1}
        )
        piece_unit, _ = UnitOfMeasure.objects.get_or_create(
            name='Piece',
            defaults={'symbol': 'pcs', 'conversion_factor': 1}
        )
        
        # Create sample products first
        products_data = [
            {
                'sku': 'RM-TIO2-25KG',
                'name': 'Titanium Dioxide',
                'product_type': 'raw_material',
                'unit_of_measure': kg_unit,
                'description': 'White pigment for paint production'
            },
            {
                'sku': 'RM-RESIN-200L',
                'name': 'Acrylic Resin',
                'product_type': 'raw_material',
                'unit_of_measure': liter_unit,
                'description': 'Base resin for paint formulation'
            },
            {
                'sku': 'FG-WHITE-1L',
                'name': 'White Paint 1L',
                'product_type': 'finished_good',
                'unit_of_measure': piece_unit,
                'description': 'Premium white paint in 1L containers'
            },
            {
                'sku': 'FG-BLUE-1L',
                'name': 'Blue Paint 1L',
                'product_type': 'finished_good',
                'unit_of_measure': piece_unit,
                'description': 'Premium blue paint in 1L containers'
            },
            {
                'sku': 'PKG-BOTTLE-1L',
                'name': '1L Plastic Bottle',
                'product_type': 'packaging',
                'unit_of_measure': piece_unit,
                'description': '1L plastic bottle for paint packaging'
            },
            {
                'sku': 'PKG-LABEL-WHITE',
                'name': 'White Paint Label',
                'product_type': 'packaging',
                'unit_of_measure': piece_unit,
                'description': 'Product label for white paint'
            },
        ]
        
        for product_data in products_data:
            product, created = Product.objects.get_or_create(
                sku=product_data['sku'],
                defaults=product_data
            )
            if created:
                self.stdout.write(f'Created product: {product.sku}')
        
        # Create sample stock items - using bulk_create to avoid signals
        stock_items_data = [
            {
                'product': Product.objects.get(sku='RM-TIO2-25KG'),
                'warehouse': Warehouse.objects.get(code='WH-RAW'),
                'batch_number': 'BATCH-TIO2-001',
                'quantity': 1500,
                'reorder_threshold': 500,
                'unit_cost': 2.50,
                'expiry_date': timezone.now().date() + timedelta(days=365),
            },
            {
                'product': Product.objects.get(sku='RM-RESIN-200L'),
                'warehouse': Warehouse.objects.get(code='WH-RAW'),
                'batch_number': 'BATCH-RESIN-001',
                'quantity': 800,
                'reorder_threshold': 200,
                'unit_cost': 1.80,
                'expiry_date': timezone.now().date() + timedelta(days=180),
            },
            {
                'product': Product.objects.get(sku='FG-WHITE-1L'),
                'warehouse': Warehouse.objects.get(code='WH-FIN'),
                'batch_number': 'BATCH-WHITE-001',
                'quantity': 2500,
                'reorder_threshold': 1000,
                'unit_cost': 8.50,
                'expiry_date': timezone.now().date() + timedelta(days=730),
            },
            {
                'product': Product.objects.get(sku='FG-BLUE-1L'),
                'warehouse': Warehouse.objects.get(code='WH-FIN'),
                'batch_number': 'BATCH-BLUE-001',
                'quantity': 800,  # Low stock
                'reorder_threshold': 1000,
                'unit_cost': 9.00,
                'expiry_date': timezone.now().date() + timedelta(days=730),
            },
            {
                'product': Product.objects.get(sku='PKG-BOTTLE-1L'),
                'warehouse': Warehouse.objects.get(code='WH-MAIN'),
                'batch_number': 'BATCH-BTL-001',
                'quantity': 3000,
                'reorder_threshold': 2000,
                'unit_cost': 0.50,
            },
            {
                'product': Product.objects.get(sku='PKG-LABEL-WHITE'),
                'warehouse': Warehouse.objects.get(code='WH-MAIN'),
                'batch_number': 'BATCH-LBL-001',
                'quantity': 4500,
                'reorder_threshold': 3000,
                'unit_cost': 0.10,
            },
        ]
        
        # Use bulk_create to avoid individual save() calls that trigger signals
        stock_items = []
        for item_data in stock_items_data:
            stock_item = StockItem(**item_data)
            stock_items.append(stock_item)
        
        StockItem.objects.bulk_create(stock_items)
        self.stdout.write(f'Created {len(stock_items)} stock items')
        
        self.stdout.write(
            self.style.SUCCESS('Successfully populated inventory with sample data!')
        )