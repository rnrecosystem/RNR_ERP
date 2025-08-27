from pydantic import BaseModel, Field, ConfigDict, validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum


class SalesBillStatus(str, Enum):
    """Sales bill status"""
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SalesBillPaymentStatus(str, Enum):
    """Payment status for sales"""
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    OVERDUE = "OVERDUE"


class SalesBillType(str, Enum):
    """Type of sale"""
    REGULAR = "REGULAR"
    WHOLESALE = "WHOLESALE"
    RETAIL = "RETAIL"
    B2B = "B2B"
    EXPORT = "EXPORT"


class TaxType(str, Enum):
    """Tax handling type"""
    INCLUDE_TAX = "INCLUDE_TAX"
    EXCLUDE_TAX = "EXCLUDE_TAX" 
    WITHOUT_TAX = "WITHOUT_TAX"


# Sales Bill Item Schemas
class SalesBillItemBase(BaseModel):
    """Base schema for sales bill item"""
    product_variant_id: int = Field(..., description="Product variant ID")
    sku_code: str = Field(..., description="Product SKU code")
    product_name: str = Field(..., description="Product name")
    product_description: Optional[str] = Field(None, description="Product description")
    hsn_code: Optional[str] = Field(None, description="HSN code for tax")
    quantity: Decimal = Field(..., description="Quantity")
    unit: str = Field("PCS", description="Unit of measurement")
    rate: Decimal = Field(..., description="Rate per unit")
    discount_percentage: Decimal = Field(0.00, description="Discount percentage")
    tax_percentage: Decimal = Field(0.00, description="Tax percentage")
    batch_number: Optional[str] = Field(None, description="Batch number")
    expiry_date: Optional[date] = Field(None, description="Expiry date")
    remarks: Optional[str] = Field(None, description="Item remarks")


class SalesBillItemCreate(SalesBillItemBase):
    """Schema for creating sales bill item"""
    item_sequence: int = Field(..., description="Line number in bill")


class SalesBillItemUpdate(BaseModel):
    """Schema for updating sales bill item"""
    product_variant_id: Optional[int] = None
    sku_code: Optional[str] = None
    product_name: Optional[str] = None
    product_description: Optional[str] = None
    hsn_code: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    rate: Optional[Decimal] = None
    discount_percentage: Optional[Decimal] = None
    tax_percentage: Optional[Decimal] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    remarks: Optional[str] = None


class SalesBillItem(SalesBillItemBase):
    """Schema for sales bill item response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    sales_bill_id: int
    item_sequence: int
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    cost_price: Optional[Decimal]
    stock_deducted: bool
    created_at: datetime
    updated_at: datetime


# Sales Bill Payment Schemas
class SalesBillPaymentBase(BaseModel):
    """Base schema for sales bill payment"""
    payment_date: date = Field(..., description="Payment date")
    payment_amount: Decimal = Field(..., description="Payment amount")
    payment_method: str = Field(..., description="Payment method (CASH, BANK, CHEQUE, etc.)")
    payment_reference: Optional[str] = Field(None, description="Payment reference/transaction ID")
    bank_account_id: Optional[int] = Field(None, description="Bank account ID")
    cheque_number: Optional[str] = Field(None, description="Cheque number")
    cheque_date: Optional[date] = Field(None, description="Cheque date")
    bank_name: Optional[str] = Field(None, description="Bank name")
    remarks: Optional[str] = Field(None, description="Payment remarks")
    receipt_number: Optional[str] = Field(None, description="Receipt number")


class SalesBillPaymentCreate(SalesBillPaymentBase):
    """Schema for creating sales bill payment"""
    pass


class SalesBillPayment(SalesBillPaymentBase):
    """Schema for sales bill payment response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    sales_bill_id: int
    payment_status: str
    clearing_date: Optional[date]
    ledger_transaction_id: Optional[int]
    accounts_updated: bool
    created_at: datetime
    updated_at: datetime
    created_by: int


# Sales Bill Main Schemas
class SalesBillBase(BaseModel):
    """Base schema for sales bill"""
    bill_date: date = Field(..., description="Bill date")
    due_date: Optional[date] = Field(None, description="Payment due date")
    bill_book_id: int = Field(..., description="Bill book ID")
    customer_id: int = Field(..., description="Customer ID")
    agent_id: Optional[int] = Field(None, description="Agent ID")
    transport_name: Optional[str] = Field(None, description="Transport company name")
    transport_details: Optional[str] = Field(None, description="Transport details")
    billing_address: Optional[str] = Field(None, description="Billing address")
    shipping_address: Optional[str] = Field(None, description="Shipping address")
    discount_percentage: Decimal = Field(0.00, description="Overall discount percentage")
    adjustment_amount: Decimal = Field(0.00, description="Adjustment amount (round off)")
    sale_type: SalesBillType = Field(SalesBillType.REGULAR, description="Type of sale")
    reference_number: Optional[str] = Field(None, description="Reference number (PO number, etc.)")
    remarks: Optional[str] = Field(None, description="Remarks")
    internal_notes: Optional[str] = Field(None, description="Internal notes")
    payment_terms: Optional[str] = Field(None, description="Payment terms")
    delivery_terms: Optional[str] = Field(None, description="Delivery terms")


class SalesBillCreate(SalesBillBase):
    """Schema for creating sales bill"""
    items: List[SalesBillItemCreate] = Field(..., description="Sales bill items")


class SalesBillUpdate(BaseModel):
    """Schema for updating sales bill"""
    bill_date: Optional[date] = None
    due_date: Optional[date] = None
    customer_id: Optional[int] = None
    agent_id: Optional[int] = None
    transport_name: Optional[str] = None
    transport_details: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    discount_percentage: Optional[Decimal] = None
    adjustment_amount: Optional[Decimal] = None
    sale_type: Optional[SalesBillType] = None
    reference_number: Optional[str] = None
    remarks: Optional[str] = None
    internal_notes: Optional[str] = None
    payment_terms: Optional[str] = None
    delivery_terms: Optional[str] = None
    status: Optional[SalesBillStatus] = None


class SalesBill(SalesBillBase):
    """Schema for sales bill response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    bill_number: str
    tax_type: TaxType
    total_item_count: int
    total_quantity: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    payment_status: SalesBillPaymentStatus
    paid_amount: Decimal
    balance_amount: Decimal
    status: SalesBillStatus
    is_active: bool
    is_printed: bool
    print_count: int
    accounts_updated: bool
    stock_updated: bool
    created_at: datetime
    updated_at: datetime
    created_by: int
    updated_by: Optional[int]
    
    # Related data
    items: List[SalesBillItem] = []
    payments: List[SalesBillPayment] = []


class SalesBillSummary(BaseModel):
    """Schema for sales bill summary/list view"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    bill_number: str
    bill_date: date
    customer_name: str
    total_item_count: int
    total_quantity: Decimal
    net_amount: Decimal
    payment_status: SalesBillPaymentStatus
    paid_amount: Decimal
    balance_amount: Decimal
    status: SalesBillStatus
    created_at: datetime


class SalesBillListResponse(BaseModel):
    """Schema for paginated sales bill list response"""
    sales_bills: List[SalesBillSummary]
    total: int
    page: int
    per_page: int
    total_amount: Decimal = Field(0.00, description="Total amount of all bills in result")
    paid_amount: Decimal = Field(0.00, description="Total paid amount")
    balance_amount: Decimal = Field(0.00, description="Total balance amount")


# Financial calculation schemas
class TaxCalculation(BaseModel):
    """Schema for tax calculation results"""
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class BillCalculation(BaseModel):
    """Schema for complete bill calculation"""
    total_item_count: int
    total_quantity: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal
    adjustment_amount: Decimal
    net_amount: Decimal
    items: List[TaxCalculation]


# Status update schemas
class SalesBillStatusUpdate(BaseModel):
    """Schema for updating sales bill status"""
    status: SalesBillStatus
    remarks: Optional[str] = Field(None, description="Remarks for status change")


class SalesBillPrintUpdate(BaseModel):
    """Schema for updating print status"""
    is_printed: bool = True
    increment_count: bool = True


# Quick create schemas for common operations
class QuickSalesBillCreate(BaseModel):
    """Schema for quick sales bill creation with minimal fields"""
    bill_book_id: int
    customer_id: int
    bill_date: date = Field(default_factory=date.today)
    items: List[dict] = Field(..., description="Simple item list with product_variant_id, quantity, rate")


# Search and filter schemas
class SalesBillSearchFilters(BaseModel):
    """Schema for sales bill search filters"""
    search: Optional[str] = None
    bill_book_id: Optional[int] = None
    customer_id: Optional[int] = None
    agent_id: Optional[int] = None
    status: Optional[SalesBillStatus] = None
    payment_status: Optional[SalesBillPaymentStatus] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
