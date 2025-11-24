from django.db import transaction
from django.utils import timezone
from apps.procurement.models import PurchaseRequisition, PurchaseRequisitionItem, GoodsReceipt
from apps.inventory.models import StockItem, ReorderAlert
from apps.products.models import Product
import logging
import uuid
import traceback

logger = logging.getLogger(__name__)

class ProcurementIntegrationService:

    @staticmethod
    def create_requisition_from_low_stock(low_stock_items, requested_by, department="Inventory"):
        """
        Create a purchase requisition from low stock items with improved error handling
        """
        try:
            logger.info(f"Creating requisition from {len(low_stock_items)} low stock items")
    
        # Log the incoming stock items for debugging
            for i, stock_item in enumerate(low_stock_items):
                logger.info(f"Stock Item {i+1}: {stock_item.product.sku}, "
                   f"Current Qty: {stock_item.quantity}, "
                   f"Reorder Threshold: {stock_item.product.reorder_threshold}")
    
            with transaction.atomic():
            # Generate requisition number
                requisition_number = f"REQ-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
                logger.info(f"Generated requisition number: {requisition_number}")
        
            # Create the requisition
                requisition = PurchaseRequisition.objects.create(
                    requisition_number=requisition_number,
                    requested_by=requested_by,
                    department=department,
                    purpose=f"Auto-generated from low stock alerts - {timezone.now().strftime('%Y-%m-%d %H:%M')}",
                    status='submitted',  # Changed from 'draft' to 'submitted'
                    total_estimated_cost=0
                )
        
                logger.info(f"Created requisition object: {requisition.id}")
        
                total_cost = 0
                items_created = []
        
            # Create requisition items
                for stock_item in low_stock_items:
                    try:
                    # FIXED: Better quantity calculation
                    # Calculate required quantity (reorder threshold - current quantity) + safety stock
                        deficit = stock_item.product.reorder_threshold - stock_item.quantity
                
                    # Ensure we're ordering at least the deficit
                        if deficit <= 0:
                        # If current stock is above threshold but still low, order minimum quantity
                            required_quantity = stock_item.product.reorder_threshold
                        else:
                            required_quantity = deficit
                  
                    # Add safety margin (20-30% of reorder threshold)
                        safety_margin = stock_item.product.reorder_threshold * 0.3
                        required_quantity += safety_margin
                
                    # Ensure minimum order quantity (at least 1)
                        if required_quantity <= 0:
                            required_quantity = max(stock_item.product.reorder_threshold, 1)
                
                    # Round to appropriate decimal places
                        if stock_item.product.unit_of_measure and stock_item.product.unit_of_measure.decimal_places == 0:
                            required_quantity = max(round(required_quantity), 1)  # At least 1
                        else:
                            required_quantity = max(round(required_quantity, 4), 0.0001)  # At least 0.0001
                
                    # Use product cost price or current unit cost
                        unit_price = stock_item.unit_cost or stock_item.product.cost_price or 0
                        if unit_price <= 0:
                        # Set a default price if none exists
                            from decimal import Decimal
                            unit_price = Decimal('1.00')
                            logger.warning(f"No unit price for {stock_item.product.sku}, using default: {unit_price}")
                
                        item_total = required_quantity * unit_price
                        total_cost += item_total
                
                    # Calculate required date (default 2 weeks)
                        required_date = timezone.now().date() + timezone.timedelta(days=14)
                
                    # Create requisition item
                        requisition_item = PurchaseRequisitionItem.objects.create(
                            requisition=requisition,
                            product=stock_item.product,
                            quantity=required_quantity,
                            unit_price=unit_price,
                            required_date=required_date,
                            notes=(
                                f"Auto-generated from low stock. "
                                f"Current: {stock_item.quantity} {stock_item.product.unit_of_measure.symbol if stock_item.product.unit_of_measure else 'units'}, "
                                f"Reorder at: {stock_item.product.reorder_threshold}, "
                                f"Warehouse: {stock_item.warehouse.code}"
                            )
                        )
                        items_created.append(requisition_item)
                
                        logger.info(f"Created requisition item for {stock_item.product.sku}: "
                           f"{required_quantity} units @ {unit_price} each")
                
                    # Update stock item procurement status
                        stock_item.procurement_status = 'ordered'
                        stock_item.save()
                
                    except Exception as item_error:
                        logger.error(f"Error creating requisition item for {stock_item.product.sku}: {str(item_error)}")
                        logger.error(traceback.format_exc())
                    # Continue with other items even if one fails
                        continue
        
            # Update total estimated cost
                requisition.total_estimated_cost = total_cost
                requisition.save()
        
            # Resolve reorder alerts for processed items
                try:
                    from apps.inventory.models import ReorderAlert
                    ReorderAlert.objects.filter(
                        stock_item__in=low_stock_items,
                        status='active'
                    ).update(
                        status='resolved',
                        notes=f"Converted to requisition {requisition_number}"
                    )
                    logger.info(f"Resolved reorder alerts for {len(low_stock_items)} items")
                except Exception as alert_error:
                    logger.error(f"Error resolving reorder alerts: {str(alert_error)}")
            # Don't fail the whole process if alert update fails
        
                logger.info(
                    f"Successfully created requisition {requisition_number} with {len(items_created)} items. "
                    f"Total cost: {total_cost}"
                )
        
            # Log all created items for verification
                for item in items_created:
                    logger.info(f"Requisition Item: {item.product.sku}, Qty: {item.quantity}, Price: {item.unit_price}")
        
                return requisition
        
        except Exception as e:
            logger.error(f"Error in create_requisition_from_low_stock: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    @staticmethod
    def get_low_stock_analysis():
        """
        Get comprehensive low stock analysis for reporting
        """
        low_stock_items = StockItem.objects.filter(
            quantity__lte=models.F('product__reorder_threshold'),
            quantity__gt=0  # Exclude out-of-stock items
        ).select_related('product', 'warehouse', 'product__unit_of_measure')
        
        analysis = {
            'total_count': low_stock_items.count(),
            'total_value_at_risk': 0,
            'total_deficit': 0,
            'by_warehouse': {},
            'by_product_type': {},
            'critical_items': [],
            'high_priority_items': [],
            'medium_priority_items': []
        }
        
        for item in low_stock_items:
            # Calculate deficit
            deficit = item.product.reorder_threshold - item.quantity
            value_at_risk = deficit * (item.unit_cost or item.product.cost_price or 0)
            
            analysis['total_deficit'] += deficit
            analysis['total_value_at_risk'] += value_at_risk
            
            # Categorize by warehouse
            warehouse_code = item.warehouse.code
            if warehouse_code not in analysis['by_warehouse']:
                analysis['by_warehouse'][warehouse_code] = {
                    'count': 0,
                    'deficit': 0,
                    'value_at_risk': 0
                }
            analysis['by_warehouse'][warehouse_code]['count'] += 1
            analysis['by_warehouse'][warehouse_code]['deficit'] += deficit
            analysis['by_warehouse'][warehouse_code]['value_at_risk'] += value_at_risk
            
            # Categorize by product type
            product_type = item.product.product_type
            if product_type not in analysis['by_product_type']:
                analysis['by_product_type'][product_type] = {
                    'count': 0,
                    'deficit': 0,
                    'value_at_risk': 0
                }
            analysis['by_product_type'][product_type]['count'] += 1
            analysis['by_product_type'][product_type]['deficit'] += deficit
            analysis['by_product_type'][product_type]['value_at_risk'] += value_at_risk
            
            # Categorize by severity
            stock_percentage = (item.quantity / item.product.reorder_threshold) * 100
            item_data = {
                'id': item.id,
                'product_sku': item.product.sku,
                'product_name': item.product.name,
                'warehouse': item.warehouse.code,
                'current_stock': float(item.quantity),
                'reorder_threshold': float(item.product.reorder_threshold),
                'deficit': float(deficit),
                'severity_percentage': stock_percentage,
                'value_at_risk': float(value_at_risk),
                'unit': item.product.unit_of_measure.symbol if item.product.unit_of_measure else 'units'
            }
            
            if stock_percentage < 10:
                analysis['critical_items'].append(item_data)
            elif stock_percentage < 25:
                analysis['high_priority_items'].append(item_data)
            else:
                analysis['medium_priority_items'].append(item_data)
        
        return analysis
    
    @staticmethod
    def process_goods_receipt(goods_receipt):
        """
        Process goods receipt and update stock quantities
        """
        try:
            with transaction.atomic():
                for receipt_item in goods_receipt.items.all():
                    stock_item, created = StockItem.objects.get_or_create(
                        product=receipt_item.po_item.product,
                        warehouse=goods_receipt.purchase_order.warehouse,  # Assuming PO has warehouse
                        batch_number=receipt_item.batch_number,
                        defaults={
                            'quantity': 0,
                            'unit_cost': receipt_item.unit_cost,
                            'reorder_threshold': receipt_item.po_item.product.reorder_threshold,
                            'procurement_status': 'received'
                        }
                    )
                    
                    # Update stock quantity
                    old_quantity = stock_item.quantity
                    stock_item.quantity += receipt_item.received_quantity
                    stock_item.unit_cost = receipt_item.unit_cost  # Update cost with latest
                    stock_item.procurement_status = 'received'
                    stock_item.save()
                    
                    # Create stock transaction
                    StockTransaction.objects.create(
                        stock_item=stock_item,
                        transaction_type='in',
                        quantity=receipt_item.received_quantity,
                        reference=f"GR-{goods_receipt.gr_number}",
                        notes=f"Goods receipt from PO {goods_receipt.purchase_order.po_number}",
                        created_by=goods_receipt.received_by
                    )
                    
                    logger.info(f"Updated stock for {stock_item.product.sku}: {old_quantity} -> {stock_item.quantity}")
                
                # Update procurement status for all related stock items
                ProcurementIntegrationService.update_procurement_status(goods_receipt.purchase_order)
                
                return True
                
        except Exception as e:
            logger.error(f"Error processing goods receipt: {str(e)}")
            raise
    
    @staticmethod
    def update_procurement_status(purchase_order):
        """
        Update procurement status based on purchase order status
        """
        try:
            for po_item in purchase_order.items.all():
                # Find all stock items for this product
                stock_items = StockItem.objects.filter(product=po_item.product)
                
                for stock_item in stock_items:
                    if purchase_order.status == 'confirmed':
                        stock_item.procurement_status = 'ordered'
                    elif purchase_order.status in ['partially_received', 'completed']:
                        stock_item.procurement_status = 'received'
                    elif purchase_order.status == 'cancelled':
                        stock_item.procurement_status = 'pending'
                    
                    stock_item.save()
                    
        except Exception as e:
            logger.error(f"Error updating procurement status: {str(e)}")