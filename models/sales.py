from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from models.user import Base
from datetime import datetime

class Sale(Base):
    """Sales master table"""
    __tablename__ = "sales"
    
    id = Column(Integer, primary_key=True, index=True)
    sale_number = Column(String(50), unique=True, nullable=False, index=True)
    sale_date = Column(Date, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    bill_book_id = Column(Integer, ForeignKey("bill_books.id"), nullable=False)  # Reference to bill book
    
    # Financial details
    subtotal = Column(Numeric(15, 2), nullable=False, default=0.00)
    tax_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    discount_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    total_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    
    # Payment details
    payment_status = Column(String(20), nullable=False, default="pending")  # pending, partial, paid
    paid_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    balance_amount = Column(Numeric(15, 2), nullable=False, default=0.00)
    
    # Additional details
    sale_type = Column(String(20), nullable=False, default="regular")  # regular, wholesale, retail
    reference_number = Column(String(100))
    notes = Column(Text)
    
    # Status and tracking
    status = Column(String(20), nullable=False, default="draft")  # draft, confirmed, shipped, completed, cancelled
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_by = Column(Integer, ForeignKey("users.id"))
    
    # Relationships
    customer = relationship("Customer", back_populates="sales")
    bill_book = relationship("BillBook", back_populates="sales")
    sale_items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    sale_payments = relationship("SalePayment", back_populates="sale", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])


class SaleItem(Base):
    """Sales item details table"""
    __tablename__ = "sale_items"
    
    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=False)
    
    # Item details
    item_description = Column(String(500))
    quantity = Column(Numeric(10, 3), nullable=False)
    unit_price = Column(Numeric(15, 2), nullable=False)
    
    # Calculations
    subtotal = Column(Numeric(15, 2), nullable=False)  # quantity * unit_price
    discount_percentage = Column(Numeric(5, 2), default=0.00)
    discount_amount = Column(Numeric(15, 2), default=0.00)
    tax_percentage = Column(Numeric(5, 2), default=0.00)
    tax_amount = Column(Numeric(15, 2), default=0.00)
    total_amount = Column(Numeric(15, 2), nullable=False)
    
    # Stock tracking
    stock_deducted = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sale = relationship("Sale", back_populates="sale_items")
    product_variant = relationship("ProductVariant", back_populates="sale_items")


class SalePayment(Base):
    """Sales payment tracking table"""
    __tablename__ = "sale_payments"
    
    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    
    # Payment details
    payment_date = Column(Date, nullable=False)
    payment_amount = Column(Numeric(15, 2), nullable=False)
    payment_method = Column(String(50), nullable=False)  # cash, bank, cheque, online, etc.
    payment_reference = Column(String(100))
    
    # Bank/Account details
    bank_account_id = Column(String(20), ForeignKey("accounts_master.account_code"))
    cheque_number = Column(String(50))
    cheque_date = Column(Date)
    
    # Status
    payment_status = Column(String(20), nullable=False, default="received")  # received, bounced, cancelled
    notes = Column(Text)
    
    # Account transaction reference (optional)
    transaction_id = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))
    
    # Relationships
    sale = relationship("Sale", back_populates="sale_payments")
    bank_account = relationship("AccountsMaster")
    creator = relationship("User")


# Enum-like classes for status choices
class SaleStatus:
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentStatus:
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"


class SaleType:
    REGULAR = "regular"
    WHOLESALE = "wholesale"
    RETAIL = "retail"


class PaymentMethod:
    CASH = "cash"
    BANK = "bank"
    CHEQUE = "cheque"
    ONLINE = "online"
    CARD = "card"
