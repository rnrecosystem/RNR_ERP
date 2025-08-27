from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Boolean, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from models.user import Base
import enum
from datetime import datetime


class SalesBillStatus(str, enum.Enum):
    """Sales bill status"""
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SalesBillPaymentStatus(str, enum.Enum):
    """Payment status for sales"""
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"


class SalesBillType(str, enum.Enum):
    """Type of sale"""
    REGULAR = "REGULAR"
    WHOLESALE = "WHOLESALE"
    RETAIL = "RETAIL"
    B2B = "B2B"
    EXPORT = "EXPORT"


class TaxType(str, enum.Enum):
    """Tax handling type (from bill book)"""
    INCLUDE_TAX = "INCLUDE_TAX"
    EXCLUDE_TAX = "EXCLUDE_TAX" 
    WITHOUT_TAX = "WITHOUT_TAX"


class SalesBill(Base):
    """
    Sales Bill Master Table
    Complete sales invoice with all financial details
    """
    __tablename__ = "sales_bills"
    
    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    bill_number = Column(String(50), unique=True, nullable=False, index=True)
    bill_date = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=True)
    
    # Bill book and tax information
    bill_book_id = Column(Integer, ForeignKey("bill_books.id"), nullable=False)
    tax_type = Column(SQLEnum(TaxType), nullable=False)  # Copied from bill book at creation
    
    # Party information
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    transport_name = Column(String(200), nullable=True)
    transport_details = Column(Text, nullable=True)
    
    # Billing address (can be different from customer default)
    billing_address = Column(Text, nullable=True)
    shipping_address = Column(Text, nullable=True)
    
    # Item summary
    total_item_count = Column(Integer, nullable=False, default=0)  # Number of different items
    total_quantity = Column(Numeric(12, 3), nullable=False, default=0.000)  # Total quantity
    
    # Financial calculations (all amounts in currency)
    gross_amount = Column(Numeric(15, 2), nullable=False, default=0.00)      # Sum of all item amounts before discount
    discount_percentage = Column(Numeric(5, 2), nullable=False, default=0.00) # Overall discount %
    discount_amount = Column(Numeric(15, 2), nullable=False, default=0.00)    # Total discount amount
    
    # Tax calculations
    taxable_amount = Column(Numeric(15, 2), nullable=False, default=0.00)     # Amount on which tax is calculated
    tax_amount = Column(Numeric(15, 2), nullable=False, default=0.00)         # Total tax amount
    
    # Adjustments and final amount
    adjustment_amount = Column(Numeric(15, 2), nullable=False, default=0.00)  # Round off or other adjustments
    net_amount = Column(Numeric(15, 2), nullable=False, default=0.00)         # Final payable amount
    
    # Payment tracking
    payment_status = Column(SQLEnum(SalesBillPaymentStatus), nullable=False, default=SalesBillPaymentStatus.PENDING)
    paid_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    balance_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    
    # Additional information
    sale_type = Column(SQLEnum(SalesBillType), nullable=False, default=SalesBillType.REGULAR)
    reference_number = Column(String(100), nullable=True)  # Customer PO number, etc.
    remarks = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)  # Internal notes not printed on invoice
    
    # Terms and conditions
    payment_terms = Column(String(200), nullable=True)  # e.g., "30 Days", "Cash on Delivery"
    delivery_terms = Column(String(200), nullable=True)
    
    # Status and workflow
    status = Column(SQLEnum(SalesBillStatus), nullable=False, default=SalesBillStatus.DRAFT)
    is_active = Column(Boolean, default=True)
    is_printed = Column(Boolean, default=False)
    print_count = Column(Integer, default=0)
    
    # Financial transaction flags
    accounts_updated = Column(Boolean, default=False)    # Whether accounts have been updated
    stock_updated = Column(Boolean, default=False)       # Whether stock has been deducted
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    bill_book = relationship("BillBook", back_populates="sales_bills")
    customer = relationship("Customer", back_populates="sales_bills")
    agent = relationship("Agent", back_populates="sales_bills")
    items = relationship("SalesBillItem", back_populates="sales_bill", cascade="all, delete-orphan")
    payments = relationship("SalesBillPayment", back_populates="sales_bill", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])


class SalesBillItem(Base):
    """
    Sales Bill Items Table
    Individual line items in a sales bill
    """
    __tablename__ = "sales_bill_items"
    
    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    sales_bill_id = Column(Integer, ForeignKey("sales_bills.id"), nullable=False)
    item_sequence = Column(Integer, nullable=False)  # Line number in bill
    
    # Product information
    product_variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=False)
    sku_code = Column(String(50), nullable=False, index=True)
    product_name = Column(String(300), nullable=False)
    product_description = Column(Text, nullable=True)
    
    # HSN and tax information
    hsn_code = Column(String(20), nullable=True)
    tax_percentage = Column(Numeric(5, 2), nullable=False, default=0.00)
    
    # Quantity and pricing
    quantity = Column(Numeric(12, 3), nullable=False)
    unit = Column(String(20), nullable=False, default="PCS")
    rate = Column(Numeric(15, 2), nullable=False)  # Rate per unit
    
    # Amount calculations
    gross_amount = Column(Numeric(15, 2), nullable=False)  # quantity * rate
    discount_percentage = Column(Numeric(5, 2), nullable=False, default=0.00)
    discount_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    
    # Tax calculations
    taxable_amount = Column(Numeric(15, 2), nullable=False)  # Amount after discount
    tax_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    total_amount = Column(Numeric(15, 2), nullable=False)    # Final line total
    
    # Stock and costing
    cost_price = Column(Numeric(15, 2), nullable=True)      # For profit calculation
    stock_deducted = Column(Boolean, default=False)
    
    # Additional details
    batch_number = Column(String(50), nullable=True)
    expiry_date = Column(Date, nullable=True)
    remarks = Column(Text, nullable=True)
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    sales_bill = relationship("SalesBill", back_populates="items")
    product_variant = relationship("ProductVariant", back_populates="sales_bill_items")


class SalesBillPayment(Base):
    """
    Sales Bill Payment Tracking
    Records all payments received against sales bills
    """
    __tablename__ = "sales_bill_payments"
    
    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    sales_bill_id = Column(Integer, ForeignKey("sales_bills.id"), nullable=False)
    
    # Payment details
    payment_date = Column(Date, nullable=False, index=True)
    payment_amount = Column(Numeric(15, 2), nullable=False)
    payment_method = Column(String(50), nullable=False)  # CASH, BANK, CHEQUE, ONLINE, UPI, CARD
    payment_reference = Column(String(100), nullable=True)  # Transaction ID, cheque number, etc.
    
    # Bank/Account details
    bank_account_id = Column(Integer, nullable=True)  # Reference to accounts_master.id
    cheque_number = Column(String(50), nullable=True)
    cheque_date = Column(Date, nullable=True)
    bank_name = Column(String(200), nullable=True)
    
    # Status and tracking
    payment_status = Column(String(20), nullable=False, default="RECEIVED")  # RECEIVED, BOUNCED, CANCELLED
    clearing_date = Column(Date, nullable=True)  # For cheques
    
    # Accounting integration
    ledger_transaction_id = Column(Integer, nullable=True)  # Link to ledger transaction
    accounts_updated = Column(Boolean, default=False)
    
    # Additional information
    remarks = Column(Text, nullable=True)
    receipt_number = Column(String(50), nullable=True)
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Relationships
    sales_bill = relationship("SalesBill", back_populates="payments")
    creator = relationship("User")


# Update related models to establish relationships
# This will be imported by other models

def update_related_models():
    """
    Function to update related models with sales bill relationships
    Call this after all models are loaded
    """
    from models.bill_book import BillBook
    from models.customers import Customer
    from models.agents import Agent
    from models.product_management import ProductVariant
    
    # Add relationships to existing models
    BillBook.sales_bills = relationship("SalesBill", back_populates="bill_book")
    Customer.sales_bills = relationship("SalesBill", back_populates="customer")
    Agent.sales_bills = relationship("SalesBill", back_populates="agent")
    ProductVariant.sales_bill_items = relationship("SalesBillItem", back_populates="product_variant")
