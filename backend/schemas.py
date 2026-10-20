from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    role: Literal["user", "rider"] = "user"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class VerifyIn(BaseModel):
    employer: str = Field(min_length=2, max_length=120)
    work_id: str = Field(min_length=3, max_length=40)
    bank_name: str = Field(min_length=2, max_length=80)
    bank_acct: str = Field(min_length=6, max_length=30)


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category: str = Field(default="Staples", max_length=40)
    price: float = Field(gt=0, le=10000)
    stock: float = Field(default=0, ge=0, le=1000000)


class OrderItemIn(BaseModel):
    product_id: int
    qty: float = Field(gt=0, le=500)   # kg


class OrderIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=50)
    address: str = Field(min_length=5, max_length=300)
    lat: Optional[float] = None
    lng: Optional[float] = None
    payment_method: Literal["credit", "instant"] = "credit"
    bulk: bool = False
    note: str = Field(default="", max_length=200)


class RiderRegisterIn(BaseModel):
    dl_number: str = Field(min_length=4, max_length=40)
    plate: str = Field(min_length=2, max_length=20)


class LocationIn(BaseModel):
    lat: float
    lng: float


class StatusIn(BaseModel):
    status: Literal["picked", "delivering", "delivered"]


class AssignIn(BaseModel):
    rider_id: int


class CreditAdjustIn(BaseModel):
    user_id: int
    limit: float = Field(ge=0, le=100000)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
