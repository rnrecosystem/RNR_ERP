from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func, text
from typing import Optional, List
from decimal import Decimal
import logging
from datetime import datetime, date

from dependencies import get_db, get_current_user
from models.sales_bills import SalesBill, SalesBillItem, SalesBillPayment, SalesBillStatus, SalesBillPaymentStatus, TaxType
from models.bill_book import BillBook
from models.customers import Customer
from models.agents import Agent
from models.product_management import ProductVariant
from models.user import User
from schemas.sales_bills import (
    SalesBillCreate,
    SalesBillUpdate,
    SalesBill as SalesBillSchema,
    SalesBillSummary,
    SalesBillListResponse,
    SalesBillItemCreate,
    SalesBillItem as SalesBillItemSchema,
    SalesBillPaymentCreate,
    SalesBillPayment as SalesBillPaymentSchema,
    SalesBillStatusUpdate,
    BillCalculation,
    TaxCalculation
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


class FinancialTransactionProcessor:
    """Handle all financial transactions in background"""
    
    @staticmethod
    def calculate_item_amounts(item_data: dict, tax_type: TaxType, bill_discount_percentage: Decimal = 0) -> dict:
        """Calculate all amounts for a single item based on tax type"""
        
        quantity = Decimal(str(item_data['quantity']))
        rate = Decimal(str(item_data['rate']))
        item_discount_percentage = Decimal(str(item_data.get('discount_percentage', 0)))
        tax_percentage = Decimal(str(item_data.get('tax_percentage', 0)))
        
        # Calculate gross amount
        gross_amount = quantity * rate
        
        # Calculate item discount
        item_discount_amount = gross_amount * (item_discount_percentage / 100)
        
        # Apply bill-level discount
        bill_discount_amount = gross_amount * (bill_discount_percentage / 100)
        
        # Total discount
        total_discount = item_discount_amount + bill_discount_amount
        
        # Amount after discount
        amount_after_discount = gross_amount - total_discount
        
        # Tax calculation based on tax type
        if tax_type == TaxType.INCLUDE_TAX and tax_percentage > 0:
            # Tax is included in rate - separate it
            tax_multiplier = 1 + (tax_percentage / 100)
            taxable_amount = amount_after_discount / tax_multiplier
            tax_amount = amount_after_discount - taxable_amount
            
        elif tax_type == TaxType.EXCLUDE_TAX and tax_percentage > 0:
            # Tax is added on top
            taxable_amount = amount_after_discount
            tax_amount = taxable_amount * (tax_percentage / 100)
            
        else:  # WITHOUT_TAX or no tax percentage
            taxable_amount = amount_after_discount
            tax_amount = Decimal('0.00')
        
        # Final total
        total_amount = taxable_amount + tax_amount
        
        return {
            'gross_amount': gross_amount,
            'discount_amount': total_discount,
            'taxable_amount': taxable_amount,
            'tax_amount': tax_amount,
            'total_amount': total_amount
        }
    
    @staticmethod
    def calculate_bill_totals(items: List[dict], adjustment_amount: Decimal = 0) -> dict:
        """Calculate total amounts for the entire bill"""
        
        total_item_count = len(items)
        total_quantity = sum(Decimal(str(item['quantity'])) for item in items)
        
        # Sum all calculated amounts
        gross_amount = sum(item['calculated_amounts']['gross_amount'] for item in items)
        discount_amount = sum(item['calculated_amounts']['discount_amount'] for item in items)
        taxable_amount = sum(item['calculated_amounts']['taxable_amount'] for item in items)
        tax_amount = sum(item['calculated_amounts']['tax_amount'] for item in items)
        
        # Calculate net amount with adjustment
        net_amount = taxable_amount + tax_amount + adjustment_amount
        
        return {
            'total_item_count': total_item_count,
            'total_quantity': total_quantity,
            'gross_amount': gross_amount,
            'discount_amount': discount_amount,
            'taxable_amount': taxable_amount,
            'tax_amount': tax_amount,
            'adjustment_amount': adjustment_amount,
            'net_amount': net_amount
        }
    
    @staticmethod
    def update_stock_ledger(item: SalesBillItem, operation: str = "ADD"):
        """Update stock ledger for sales transactions"""
        # This will be implemented based on your stock ledger structure
        # For now, just mark as stock updated
        logger.info(f"Stock {operation}: {item.sku_code} - Qty: {item.quantity}")
        return True
    
    @staticmethod
    def update_customer_ledger(sales_bill: SalesBill, operation: str = "ADD"):
        """Update customer ledger for sales transactions"""
        # This will create/update customer ledger entries
        logger.info(f"Customer ledger {operation}: {sales_bill.bill_number} - Amount: {sales_bill.net_amount}")
        return True
    
    @staticmethod
    def process_financial_transactions(sales_bill: SalesBill, db: Session):
        """Process all financial transactions for a sales bill"""
        try:
            # Update stock for each item
            for item in sales_bill.items:
                FinancialTransactionProcessor.update_stock_ledger(item, "DEDUCT")
                item.stock_deducted = True
            
            # Update customer ledger
            FinancialTransactionProcessor.update_customer_ledger(sales_bill, "ADD")
            
            # Mark as financially processed
            sales_bill.stock_updated = True
            sales_bill.accounts_updated = True
            
            db.commit()
            logger.info(f"Financial transactions processed for bill {sales_bill.bill_number}")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to process financial transactions: {str(e)}")
            raise


@router.post("/", response_model=SalesBillSchema)
async def create_sales_bill(
    sales_bill_data: SalesBillCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new sales bill with automatic calculations and financial processing"""
    
    try:
        # Validate bill book and generate bill number
        bill_book = db.query(BillBook).filter(BillBook.id == sales_bill_data.bill_book_id).first()
        if not bill_book:
            raise HTTPException(status_code=404, detail="Bill book not found")
        
        if bill_book.status != "ACTIVE":
            raise HTTPException(status_code=400, detail="Bill book is not active")
        
        # Generate bill number
        bill_book.last_bill_no += 1
        bill_number = f"{bill_book.prefix}{bill_book.last_bill_no:04d}"
        
        # Validate customer
        customer = db.query(Customer).filter(Customer.id == sales_bill_data.customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Validate agent if provided
        if sales_bill_data.agent_id:
            agent = db.query(Agent).filter(Agent.id == sales_bill_data.agent_id).first()
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
        
        # Prepare items with calculations
        processed_items = []
        for item_data in sales_bill_data.items:
            # Validate product variant
            product_variant = db.query(ProductVariant).filter(
                ProductVariant.id == item_data.product_variant_id
            ).first()
            if not product_variant:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Product variant {item_data.product_variant_id} not found"
                )
            
            # Calculate amounts for this item
            item_dict = item_data.model_dump()
            calculated_amounts = FinancialTransactionProcessor.calculate_item_amounts(
                item_dict, bill_book.tax_type, sales_bill_data.discount_percentage
            )
            
            item_dict['calculated_amounts'] = calculated_amounts
            item_dict['product_variant'] = product_variant
            processed_items.append(item_dict)
        
        # Calculate bill totals
        bill_totals = FinancialTransactionProcessor.calculate_bill_totals(
            processed_items, sales_bill_data.adjustment_amount
        )
        
        # Create sales bill
        db_sales_bill = SalesBill(
            bill_number=bill_number,
            tax_type=bill_book.tax_type,
            created_by=current_user.id,
            **sales_bill_data.model_dump(exclude={'items'}),
            **bill_totals,
            balance_amount=bill_totals['net_amount']  # Initially, full amount is balance
        )
        
        db.add(db_sales_bill)
        db.flush()  # Get the ID
        
        # Create sales bill items
        for item_data in processed_items:
            calculated = item_data['calculated_amounts']
            product_variant = item_data['product_variant']
            
            db_item = SalesBillItem(
                sales_bill_id=db_sales_bill.id,
                product_variant_id=item_data['product_variant_id'],
                sku_code=product_variant.sku,
                product_name=product_variant.product.product_name,
                item_sequence=item_data['item_sequence'],
                quantity=item_data['quantity'],
                rate=item_data['rate'],
                unit=item_data.get('unit', 'PCS'),
                discount_percentage=item_data.get('discount_percentage', 0),
                tax_percentage=item_data.get('tax_percentage', 0),
                hsn_code=item_data.get('hsn_code'),
                product_description=item_data.get('product_description'),
                batch_number=item_data.get('batch_number'),
                expiry_date=item_data.get('expiry_date'),
                remarks=item_data.get('remarks'),
                **calculated
            )
            db.add(db_item)
        
        db.commit()
        db.refresh(db_sales_bill)
        
        # Process financial transactions in background
        background_tasks.add_task(
            FinancialTransactionProcessor.process_financial_transactions,
            db_sales_bill,
            db
        )
        
        logger.info(f"Created sales bill {bill_number} for customer {customer.customer_name}")
        
        # Load with relationships for response
        sales_bill_with_relations = db.query(SalesBill).options(
            joinedload(SalesBill.items),
            joinedload(SalesBill.payments)
        ).filter(SalesBill.id == db_sales_bill.id).first()
        
        return sales_bill_with_relations
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating sales bill: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create sales bill: {str(e)}"
        )


@router.get("/", response_model=SalesBillListResponse)
async def list_sales_bills(
    search: Optional[str] = Query(None, description="Search in bill number, customer name"),
    bill_book_id: Optional[int] = Query(None, description="Filter by bill book"),
    customer_id: Optional[int] = Query(None, description="Filter by customer"),
    status: Optional[SalesBillStatus] = Query(None, description="Filter by status"),
    payment_status: Optional[SalesBillPaymentStatus] = Query(None, description="Filter by payment status"),
    from_date: Optional[date] = Query(None, description="From date"),
    to_date: Optional[date] = Query(None, description="To date"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List sales bills with filtering and pagination"""
    
    try:
        query = db.query(SalesBill).join(Customer).filter(SalesBill.is_active == True)
        
        # Apply filters
        if search:
            search_filter = f"%{search}%"
            query = query.filter(
                or_(
                    SalesBill.bill_number.ilike(search_filter),
                    Customer.customer_name.ilike(search_filter),
                    SalesBill.reference_number.ilike(search_filter)
                )
            )
        
        if bill_book_id:
            query = query.filter(SalesBill.bill_book_id == bill_book_id)
        
        if customer_id:
            query = query.filter(SalesBill.customer_id == customer_id)
        
        if status:
            query = query.filter(SalesBill.status == status)
        
        if payment_status:
            query = query.filter(SalesBill.payment_status == payment_status)
        
        if from_date:
            query = query.filter(SalesBill.bill_date >= from_date)
        
        if to_date:
            query = query.filter(SalesBill.bill_date <= to_date)
        
        # Get total count and amounts
        total = query.count()
        
        # Calculate summary amounts
        amounts_query = query.with_entities(
            func.sum(SalesBill.net_amount).label('total_amount'),
            func.sum(SalesBill.paid_amount).label('paid_amount'),
            func.sum(SalesBill.balance_amount).label('balance_amount')
        ).first()
        
        # Apply pagination and get results
        sales_bills = query.offset((page - 1) * per_page).limit(per_page).all()
        
        # Convert to summary format
        summaries = []
        for bill in sales_bills:
            summary = SalesBillSummary(
                id=bill.id,
                bill_number=bill.bill_number,
                bill_date=bill.bill_date,
                customer_name=bill.customer.customer_name,
                total_item_count=bill.total_item_count,
                total_quantity=bill.total_quantity,
                net_amount=bill.net_amount,
                payment_status=bill.payment_status,
                paid_amount=bill.paid_amount,
                balance_amount=bill.balance_amount,
                status=bill.status,
                created_at=bill.created_at
            )
            summaries.append(summary)
        
        return SalesBillListResponse(
            sales_bills=summaries,
            total=total,
            page=page,
            per_page=per_page,
            total_amount=amounts_query.total_amount or 0,
            paid_amount=amounts_query.paid_amount or 0,
            balance_amount=amounts_query.balance_amount or 0
        )
        
    except Exception as e:
        logger.error(f"Error listing sales bills: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sales bills: {str(e)}"
        )


@router.get("/{sales_bill_id}", response_model=SalesBillSchema)
async def get_sales_bill(
    sales_bill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific sales bill with all details"""
    
    try:
        sales_bill = db.query(SalesBill).options(
            joinedload(SalesBill.items),
            joinedload(SalesBill.payments),
            joinedload(SalesBill.customer),
            joinedload(SalesBill.agent),
            joinedload(SalesBill.bill_book)
        ).filter(SalesBill.id == sales_bill_id).first()
        
        if not sales_bill:
            raise HTTPException(status_code=404, detail="Sales bill not found")
        
        return sales_bill
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving sales bill: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve sales bill: {str(e)}"
        )


# Additional endpoints for payments, status updates, calculations etc.
@router.post("/{sales_bill_id}/payments", response_model=SalesBillPaymentSchema)
async def add_payment(
    sales_bill_id: int,
    payment_data: SalesBillPaymentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a payment to a sales bill"""
    
    try:
        # Validate sales bill
        sales_bill = db.query(SalesBill).filter(SalesBill.id == sales_bill_id).first()
        if not sales_bill:
            raise HTTPException(status_code=404, detail="Sales bill not found")
        
        # Validate payment amount
        if payment_data.payment_amount <= 0:
            raise HTTPException(status_code=400, detail="Payment amount must be positive")
        
        if payment_data.payment_amount > sales_bill.balance_amount:
            raise HTTPException(status_code=400, detail="Payment amount exceeds balance amount")
        
        # Create payment record
        db_payment = SalesBillPayment(
            sales_bill_id=sales_bill_id,
            created_by=current_user.id,
            **payment_data.model_dump()
        )
        
        db.add(db_payment)
        
        # Update sales bill payment status
        sales_bill.paid_amount += payment_data.payment_amount
        sales_bill.balance_amount -= payment_data.payment_amount
        
        if sales_bill.balance_amount <= 0:
            sales_bill.payment_status = SalesBillPaymentStatus.PAID
        elif sales_bill.paid_amount > 0:
            sales_bill.payment_status = SalesBillPaymentStatus.PARTIAL
        
        db.commit()
        db.refresh(db_payment)
        
        logger.info(f"Added payment of {payment_data.payment_amount} to bill {sales_bill.bill_number}")
        
        return db_payment
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding payment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add payment: {str(e)}"
        )


# Add more endpoints for update, delete, status changes, etc.
# This is the foundation - you can expand based on your needs
