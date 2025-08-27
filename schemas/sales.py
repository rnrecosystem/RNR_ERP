from pydantic import BaseModel, Field, validator
from typing import List, Optional
from decimal import Decimal
from datetime import date, datetime
from enum import Enum


# Enums
class SaleStatusEnum(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentStatusEnum(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"


class SaleTypeEnum(str, Enum):
    REGULAR = "regular"
    WHOLESALE = "wholesale"
    RETAIL = "retail"


class PaymentMethodEnum(str, Enum):
    CASH = "cash"
    BANK = "bank"
    CHEQUE = "cheque"
    ONLINE = "online"
    CARD = "card"


# Base schemas
class SaleItemBase(BaseModel):
    product_variant_id: int
    item_description: Optional[str] = None
    quantity: Decimal = Field(..., gt=0, description="Quantity must be greater than 0")
    unit_price: Decimal = Field(..., gt=0, description="Unit price must be greater than 0")
    discount_percentage: Optional[Decimal] = Field(default=0.00, ge=0, le=100)
    discount_amount: Optional[Decimal] = Field(default=0.00, ge=0)
    tax_percentage: Optional[Decimal] = Field(default=0.00, ge=0, le=100)
    tax_amount: Optional[Decimal] = Field(default=0.00, ge=0)


class SaleItemCreate(SaleItemBase):
    pass


class SaleItemUpdate(BaseModel):
    product_variant_id: Optional[int] = None
    item_description: Optional[str] = None
    quantity: Optional[Decimal] = Field(None, gt=0)
    unit_price: Optional[Decimal] = Field(None, gt=0)
    discount_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    discount_amount: Optional[Decimal] = Field(None, ge=0)
    tax_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    tax_amount: Optional[Decimal] = Field(None, ge=0)


class SaleItem(SaleItemBase):
    id: int
    sale_id: int
    subtotal: Decimal
    total_amount: Decimal
    stock_deducted: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Sale Payment schemas
class SalePaymentBase(BaseModel):
    payment_date: date
    payment_amount: Decimal = Field(..., gt=0, description="Payment amount must be greater than 0")
    payment_method: PaymentMethodEnum
    payment_reference: Optional[str] = None
    bank_account_id: Optional[str] = None
    cheque_number: Optional[str] = None
    cheque_date: Optional[date] = None
    notes: Optional[str] = None


class SalePaymentCreate(SalePaymentBase):
    pass


class SalePaymentUpdate(BaseModel):
    payment_date: Optional[date] = None
    payment_amount: Optional[Decimal] = Field(None, gt=0)
    payment_method: Optional[PaymentMethodEnum] = None
    payment_reference: Optional[str] = None
    bank_account_id: Optional[str] = None
    cheque_number: Optional[str] = None
    cheque_date: Optional[date] = None
    payment_status: Optional[str] = None
    notes: Optional[str] = None


class SalePayment(SalePaymentBase):
    id: int
    sale_id: int
    payment_status: str
    transaction_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Sale schemas
class SaleBase(BaseModel):
    customer_id: int
    sale_date: date
    sale_type: Optional[SaleTypeEnum] = SaleTypeEnum.REGULAR
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    discount_amount: Optional[Decimal] = Field(default=0.00, ge=0)
    tax_amount: Optional[Decimal] = Field(default=0.00, ge=0)


class SaleCreate(SaleBase):
    sale_items: List[SaleItemCreate] = Field(..., min_items=1, description="At least one item is required")
    
    @validator('sale_items')
    def validate_sale_items(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one sale item is required')
        return v


class SaleUpdate(BaseModel):
    customer_id: Optional[int] = None
    sale_date: Optional[date] = None
    sale_type: Optional[SaleTypeEnum] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[SaleStatusEnum] = None
    discount_amount: Optional[Decimal] = Field(None, ge=0)
    tax_amount: Optional[Decimal] = Field(None, ge=0)


class Sale(SaleBase):
    id: int
    sale_number: str
    subtotal: Decimal
    total_amount: Decimal
    payment_status: str
    paid_amount: Decimal
    balance_amount: Decimal
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    
    class Config:
        from_attributes = True


class SaleWithItems(Sale):
    sale_items: List[SaleItem] = []
    sale_payments: List[SalePayment] = []


class SaleWithDetails(SaleWithItems):
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    creator_name: Optional[str] = None
    updater_name: Optional[str] = None


# Bulk operations
class BulkSaleItemCreate(BaseModel):
    sale_id: int
    items: List[SaleItemCreate]


class BulkSalePaymentCreate(BaseModel):
    sale_id: int
    payments: List[SalePaymentCreate]


# Search and filter schemas
class SaleSearchFilter(BaseModel):
    sale_number: Optional[str] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    sale_date_from: Optional[date] = None
    sale_date_to: Optional[date] = None
    status: Optional[SaleStatusEnum] = None
    payment_status: Optional[PaymentStatusEnum] = None
    sale_type: Optional[SaleTypeEnum] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    is_active: Optional[bool] = True


class SaleItemSearchFilter(BaseModel):
    sale_id: Optional[int] = None
    product_variant_id: Optional[int] = None
    item_description: Optional[str] = None


# Response schemas
class SaleListResponse(BaseModel):
    sales: List[SaleWithDetails]
    total: int
    page: int
    size: int
    pages: int


class SaleItemListResponse(BaseModel):
    items: List[SaleItem]
    total: int


class SalePaymentListResponse(BaseModel):
    payments: List[SalePayment]
    total: int


# Dashboard and reporting schemas
class SaleSummary(BaseModel):
    total_sales: int
    total_amount: Decimal
    paid_amount: Decimal
    pending_amount: Decimal
    today_sales: int
    today_amount: Decimal
    month_sales: int
    month_amount: Decimal


class SalePerformanceReport(BaseModel):
    customer_id: int
    customer_name: str
    total_orders: int
    total_amount: Decimal
    paid_amount: Decimal
    pending_amount: Decimal
    last_order_date: Optional[date] = None


class SaleStatusSummary(BaseModel):
    draft: int
    confirmed: int
    shipped: int
    completed: int
    cancelled: int
    total: int


# Transaction integration schemas
class SaleAccountTransaction(BaseModel):
    sale_id: int
    transaction_type: str  # sale_entry, payment_entry
    amount: Decimal
    description: str
    debit_account_id: int
    credit_account_id: int
