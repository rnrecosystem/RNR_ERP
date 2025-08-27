from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func
from typing import List, Optional
from decimal import Decimal
from datetime import date, datetime
import logging

from dependencies import get_db
from models.sales import Sale, SaleItem, SalePayment
from models.product_management import ProductVariant, ProductStockLedger, StockMovementType
from models.customers import Customer
from models.accounts import Account
from models.ledger_transaction import LedgerTransaction
from schemas.sales import (
    # Sale schemas
    Sale as SaleSchema,
    SaleCreate,
    SaleUpdate,
    SaleWithItems,
    SaleWithDetails,
    # Sale item schemas
    SaleItem as SaleItemSchema,
    SaleItemCreate,
    SaleItemUpdate,
    BulkSaleItemCreate,
    # Sale payment schemas
    SalePayment as SalePaymentSchema,
    SalePaymentCreate,
    SalePaymentUpdate,
    BulkSalePaymentCreate,
    # Search and response schemas
    SaleSearchFilter,
    SaleItemSearchFilter,
    SaleListResponse,
    SaleItemListResponse,
    SalePaymentListResponse,
    # Summary and reporting
    SaleSummary,
    SalePerformanceReport,
    SaleStatusSummary,
    # Transaction schema
    SaleAccountTransaction
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


def generate_sale_number(db: Session) -> str:
    """Generate unique sale number"""
    try:
        # Get the latest sale number
        latest_sale = db.query(Sale).order_by(desc(Sale.id)).first()
        if latest_sale and latest_sale.sale_number:
            # Extract number from sale number (assuming format SAL-YYYY-XXXX)
            try:
                current_year = datetime.now().year
                latest_num_str = latest_sale.sale_number.split('-')[-1]
                next_num = int(latest_num_str) + 1
                return f"SAL-{current_year}-{next_num:04d}"
            except (ValueError, IndexError):
                # If parsing fails, start with 0001
                return f"SAL-{datetime.now().year}-0001"
        else:
            return f"SAL-{datetime.now().year}-0001"
    except Exception as e:
        logger.error(f"Error generating sale number: {str(e)}")
        return f"SAL-{datetime.now().year}-{datetime.now().microsecond:04d}"


def calculate_sale_totals(sale_items: List[SaleItemCreate]) -> tuple:
    """Calculate sale totals from items"""
    subtotal = sum(item.quantity * item.unit_price for item in sale_items)
    total_discount = sum(item.discount_amount or 0 for item in sale_items)
    total_tax = sum(item.tax_amount or 0 for item in sale_items)
    total_amount = subtotal - total_discount + total_tax
    
    return subtotal, total_discount, total_tax, total_amount


def create_stock_transaction(db: Session, sale_item: SaleItem, movement_type: str = "outward"):
    """Create stock ledger transaction for sale item"""
    try:
        # Get current stock balance
        current_stock = db.query(ProductStockLedger).filter(
            ProductStockLedger.product_variant_id == sale_item.product_variant_id
        ).order_by(desc(ProductStockLedger.id)).first()
        
        balance_quantity = (current_stock.balance_quantity if current_stock else 0) - sale_item.quantity
        
        # Create stock ledger entry
        stock_entry = ProductStockLedger(
            product_variant_id=sale_item.product_variant_id,
            movement_type=movement_type,
            reference_type="sale",
            reference_id=sale_item.sale_id,
            quantity=sale_item.quantity,
            balance_quantity=balance_quantity,
            rate=sale_item.unit_price,
            value=sale_item.total_amount,
            transaction_date=date.today(),
            description=f"Stock outward for sale #{sale_item.sale.sale_number}"
        )
        
        db.add(stock_entry)
        
        # Update sale item stock deduction status
        sale_item.stock_deducted = True
        
        logger.info(f"Stock transaction created for variant {sale_item.product_variant_id}, quantity: {sale_item.quantity}")
        
    except Exception as e:
        logger.error(f"Error creating stock transaction: {str(e)}")
        raise


def create_account_transaction(db: Session, sale: Sale, transaction_type: str, amount: Decimal, payment_id: int = None):
    """Create accounting transaction for sale"""
    try:
        # Get customer account (assuming customers have ledger accounts)
        customer_account = db.query(Account).filter(
            Account.account_name.ilike(f"%{sale.customer.name}%")
        ).first()
        
        # Get sales account (assuming there's a sales revenue account)
        sales_account = db.query(Account).filter(
            Account.account_name.ilike("%sales%"),
            Account.account_type == "revenue"
        ).first()
        
        if not sales_account:
            logger.warning("Sales account not found, skipping transaction")
            return
        
        if transaction_type == "sale_entry":
            # Debit Customer Account, Credit Sales Account
            description = f"Sale entry for {sale.sale_number}"
            debit_account_id = customer_account.id if customer_account else None
            credit_account_id = sales_account.id
        
        elif transaction_type == "payment_entry":
            # Debit Cash/Bank Account, Credit Customer Account
            payment = db.query(SalePayment).filter(SalePayment.id == payment_id).first()
            if not payment:
                return
                
            description = f"Payment received for {sale.sale_number}"
            debit_account_id = payment.bank_account_id if payment.bank_account_id else None
            credit_account_id = customer_account.id if customer_account else None
        
        else:
            logger.warning(f"Unknown transaction type: {transaction_type}")
            return
        
        # Create ledger transaction
        if debit_account_id and credit_account_id:
            transaction = LedgerTransaction(
                transaction_date=date.today(),
                reference_type="sale",
                reference_id=sale.id,
                debit_account_id=debit_account_id,
                credit_account_id=credit_account_id,
                amount=amount,
                description=description
            )
            
            db.add(transaction)
            logger.info(f"Account transaction created: {description}")
            return transaction
        
    except Exception as e:
        logger.error(f"Error creating account transaction: {str(e)}")
        return None


# ================================
# SALE ROUTES
# ================================

@router.post("/", response_model=SaleWithItems)
def create_sale(
    sale_data: SaleCreate,
    db: Session = Depends(get_db)
):
    """Create a new sale with items."""
    try:
        db.begin()
        
        # Validate customer exists
        customer = db.query(Customer).filter(Customer.id == sale_data.customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Calculate totals
        subtotal, total_discount, total_tax, total_amount = calculate_sale_totals(sale_data.sale_items)
        
        # Override with manual amounts if provided
        if sale_data.discount_amount is not None:
            total_discount = sale_data.discount_amount
        if sale_data.tax_amount is not None:
            total_tax = sale_data.tax_amount
        
        final_total = subtotal - total_discount + total_tax
        
        # Create sale
        db_sale = Sale(
            sale_number=generate_sale_number(db),
            customer_id=sale_data.customer_id,
            sale_date=sale_data.sale_date,
            sale_type=sale_data.sale_type,
            reference_number=sale_data.reference_number,
            notes=sale_data.notes,
            subtotal=subtotal,
            discount_amount=total_discount,
            tax_amount=total_tax,
            total_amount=final_total,
            balance_amount=final_total,
            payment_status="pending",
            status="draft"
        )
        
        db.add(db_sale)
        db.flush()  # Get the sale ID
        
        # Create sale items
        for item_data in sale_data.sale_items:
            # Validate product variant
            variant = db.query(ProductVariant).filter(
                ProductVariant.id == item_data.product_variant_id
            ).first()
            if not variant:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Product variant {item_data.product_variant_id} not found"
                )
            
            # Calculate item totals
            item_subtotal = item_data.quantity * item_data.unit_price
            item_discount = item_data.discount_amount or (item_subtotal * (item_data.discount_percentage or 0) / 100)
            item_tax = item_data.tax_amount or ((item_subtotal - item_discount) * (item_data.tax_percentage or 0) / 100)
            item_total = item_subtotal - item_discount + item_tax
            
            db_item = SaleItem(
                sale_id=db_sale.id,
                product_variant_id=item_data.product_variant_id,
                item_description=item_data.item_description,
                quantity=item_data.quantity,
                unit_price=item_data.unit_price,
                subtotal=item_subtotal,
                discount_percentage=item_data.discount_percentage or 0,
                discount_amount=item_discount,
                tax_percentage=item_data.tax_percentage or 0,
                tax_amount=item_tax,
                total_amount=item_total
            )
            
            db.add(db_item)
        
        db.commit()
        
        # Create accounting transaction
        create_account_transaction(db, db_sale, "sale_entry", final_total)
        db.commit()
        
        # Reload with relationships
        db.refresh(db_sale)
        logger.info(f"Created sale: {db_sale.sale_number}")
        
        return db_sale
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating sale: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create sale: {str(e)}"
        )


@router.get("/", response_model=SaleListResponse)
def list_sales(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    search_filter: Optional[str] = Query(None, description="General search filter"),
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    payment_status: Optional[str] = Query(None, description="Filter by payment status"),
    sale_date_from: Optional[date] = Query(None, description="Filter from date"),
    sale_date_to: Optional[date] = Query(None, description="Filter to date"),
    is_active: bool = Query(True, description="Filter active sales"),
    db: Session = Depends(get_db)
):
    """List sales with filtering and pagination."""
    try:
        query = db.query(Sale).options(
            joinedload(Sale.customer),
            joinedload(Sale.creator),
            joinedload(Sale.updater)
        )
        
        # Apply filters
        if is_active is not None:
            query = query.filter(Sale.is_active == is_active)
            
        if customer_id:
            query = query.filter(Sale.customer_id == customer_id)
            
        if status:
            query = query.filter(Sale.status == status)
            
        if payment_status:
            query = query.filter(Sale.payment_status == payment_status)
            
        if sale_date_from:
            query = query.filter(Sale.sale_date >= sale_date_from)
            
        if sale_date_to:
            query = query.filter(Sale.sale_date <= sale_date_to)
            
        if search_filter:
            search_term = f"%{search_filter}%"
            query = query.join(Customer).filter(
                or_(
                    Sale.sale_number.ilike(search_term),
                    Sale.reference_number.ilike(search_term),
                    Customer.name.ilike(search_term),
                    Sale.notes.ilike(search_term)
                )
            )
        
        # Get total count
        total = query.count()
        
        # Apply pagination and get results
        sales = query.order_by(desc(Sale.created_at)).offset(skip).limit(limit).all()
        
        # Transform to response format
        sales_with_details = []
        for sale in sales:
            sale_dict = {
                **sale.__dict__,
                "customer_name": sale.customer.name if sale.customer else None,
                "customer_code": sale.customer.code if sale.customer else None,
                "creator_name": sale.creator.username if sale.creator else None,
                "updater_name": sale.updater.username if sale.updater else None,
            }
            sales_with_details.append(sale_dict)
        
        return SaleListResponse(
            sales=sales_with_details,
            total=total,
            page=skip // limit + 1,
            size=limit,
            pages=(total + limit - 1) // limit
        )
        
    except Exception as e:
        logger.error(f"Error listing sales: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sales: {str(e)}"
        )


@router.get("/{sale_id}", response_model=SaleWithItems)
def get_sale(sale_id: int, db: Session = Depends(get_db)):
    """Get a specific sale with items and payments."""
    sale = db.query(Sale).options(
        joinedload(Sale.customer),
        joinedload(Sale.sale_items).joinedload(SaleItem.product_variant),
        joinedload(Sale.sale_payments),
        joinedload(Sale.creator),
        joinedload(Sale.updater)
    ).filter(Sale.id == sale_id).first()
    
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    
    return sale


@router.put("/{sale_id}", response_model=SaleWithItems)
def update_sale(
    sale_id: int,
    sale_update: SaleUpdate,
    db: Session = Depends(get_db)
):
    """Update a sale."""
    try:
        db_sale = db.query(Sale).filter(Sale.id == sale_id).first()
        if not db_sale:
            raise HTTPException(status_code=404, detail="Sale not found")
        
        # Don't allow updating completed or cancelled sales
        if db_sale.status in ["completed", "cancelled"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot update {db_sale.status} sale"
            )
        
        # Update fields
        update_data = sale_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_sale, field, value)
        
        db_sale.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_sale)
        
        logger.info(f"Updated sale: {db_sale.sale_number}")
        return db_sale
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating sale: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update sale: {str(e)}"
        )


@router.post("/{sale_id}/confirm")
def confirm_sale(sale_id: int, db: Session = Depends(get_db)):
    """Confirm a sale and deduct stock."""
    try:
        db.begin()
        
        sale = db.query(Sale).options(
            joinedload(Sale.sale_items)
        ).filter(Sale.id == sale_id).first()
        
        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")
        
        if sale.status != "draft":
            raise HTTPException(status_code=400, detail="Only draft sales can be confirmed")
        
        # Deduct stock for each item
        for item in sale.sale_items:
            if not item.stock_deducted:
                create_stock_transaction(db, item, "outward")
        
        # Update sale status
        sale.status = "confirmed"
        sale.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Confirmed sale: {sale.sale_number}")
        return {"message": "Sale confirmed successfully", "sale_number": sale.sale_number}
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error confirming sale: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to confirm sale: {str(e)}"
        )


# ================================
# SALE PAYMENT ROUTES
# ================================

@router.post("/{sale_id}/payments/", response_model=SalePaymentSchema)
def create_sale_payment(
    sale_id: int,
    payment_data: SalePaymentCreate,
    db: Session = Depends(get_db)
):
    """Create a payment for a sale."""
    try:
        # Validate sale exists
        sale = db.query(Sale).filter(Sale.id == sale_id).first()
        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")
        
        # Check if payment amount doesn't exceed balance
        if payment_data.payment_amount > sale.balance_amount:
            raise HTTPException(
                status_code=400, 
                detail=f"Payment amount ({payment_data.payment_amount}) exceeds balance ({sale.balance_amount})"
            )
        
        # Create payment
        db_payment = SalePayment(
            sale_id=sale_id,
            payment_date=payment_data.payment_date,
            payment_amount=payment_data.payment_amount,
            payment_method=payment_data.payment_method,
            payment_reference=payment_data.payment_reference,
            bank_account_id=payment_data.bank_account_id,
            cheque_number=payment_data.cheque_number,
            cheque_date=payment_data.cheque_date,
            notes=payment_data.notes,
            payment_status="received"
        )
        
        db.add(db_payment)
        db.flush()
        
        # Update sale payment status and amounts
        sale.paid_amount += payment_data.payment_amount
        sale.balance_amount -= payment_data.payment_amount
        
        if sale.balance_amount <= 0:
            sale.payment_status = "paid"
        else:
            sale.payment_status = "partial"
        
        # Create accounting transaction
        transaction = create_account_transaction(db, sale, "payment_entry", payment_data.payment_amount, db_payment.id)
        if transaction:
            db_payment.transaction_id = transaction.id
        
        db.commit()
        db.refresh(db_payment)
        
        logger.info(f"Created payment for sale {sale.sale_number}: {payment_data.payment_amount}")
        return db_payment
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating sale payment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create sale payment: {str(e)}"
        )


@router.get("/{sale_id}/payments/", response_model=SalePaymentListResponse)
def list_sale_payments(
    sale_id: int,
    db: Session = Depends(get_db)
):
    """List payments for a specific sale."""
    try:
        # Validate sale exists
        sale = db.query(Sale).filter(Sale.id == sale_id).first()
        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")
        
        payments = db.query(SalePayment).filter(
            SalePayment.sale_id == sale_id
        ).order_by(desc(SalePayment.payment_date)).all()
        
        return SalePaymentListResponse(
            payments=payments,
            total=len(payments)
        )
        
    except Exception as e:
        logger.error(f"Error listing sale payments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list sale payments: {str(e)}"
        )


# ================================
# REPORTING ROUTES
# ================================

@router.get("/reports/summary", response_model=SaleSummary)
def get_sale_summary(db: Session = Depends(get_db)):
    """Get sales summary statistics."""
    try:
        today = date.today()
        month_start = date(today.year, today.month, 1)
        
        # Total statistics
        total_query = db.query(
            func.count(Sale.id).label("total_sales"),
            func.sum(Sale.total_amount).label("total_amount"),
            func.sum(Sale.paid_amount).label("paid_amount")
        ).filter(Sale.is_active == True)
        
        total_stats = total_query.first()
        
        # Today statistics
        today_query = db.query(
            func.count(Sale.id).label("today_sales"),
            func.sum(Sale.total_amount).label("today_amount")
        ).filter(
            Sale.is_active == True,
            Sale.sale_date == today
        )
        
        today_stats = today_query.first()
        
        # Month statistics
        month_query = db.query(
            func.count(Sale.id).label("month_sales"),
            func.sum(Sale.total_amount).label("month_amount")
        ).filter(
            Sale.is_active == True,
            Sale.sale_date >= month_start
        )
        
        month_stats = month_query.first()
        
        return SaleSummary(
            total_sales=total_stats.total_sales or 0,
            total_amount=total_stats.total_amount or 0,
            paid_amount=total_stats.paid_amount or 0,
            pending_amount=(total_stats.total_amount or 0) - (total_stats.paid_amount or 0),
            today_sales=today_stats.today_sales or 0,
            today_amount=today_stats.today_amount or 0,
            month_sales=month_stats.month_sales or 0,
            month_amount=month_stats.month_amount or 0
        )
        
    except Exception as e:
        logger.error(f"Error getting sale summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sale summary: {str(e)}"
        )


@router.get("/reports/status-summary", response_model=SaleStatusSummary)
def get_sale_status_summary(db: Session = Depends(get_db)):
    """Get sales count by status."""
    try:
        status_counts = db.query(
            Sale.status,
            func.count(Sale.id).label("count")
        ).filter(
            Sale.is_active == True
        ).group_by(Sale.status).all()
        
        counts = {status: count for status, count in status_counts}
        
        return SaleStatusSummary(
            draft=counts.get("draft", 0),
            confirmed=counts.get("confirmed", 0),
            shipped=counts.get("shipped", 0),
            completed=counts.get("completed", 0),
            cancelled=counts.get("cancelled", 0),
            total=sum(counts.values())
        )
        
    except Exception as e:
        logger.error(f"Error getting sale status summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sale status summary: {str(e)}"
        )
