from pydantic import BaseModel,EmailStr, Field

class ProductOut(BaseModel):
    product_id: int
    product_name: str
    category_name: str
    price: float
    stock: int

class OrderCreate(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)

class OrderItemOut(BaseModel):
    product_id: int
    product_name: str
    unit_price: float
    quantity: int
    total_price: float

class OrderOut(BaseModel):
    order_id: int
    user_id: int
    items: list[OrderItemOut]
    order_total: float

class UserCreate(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(default="")
    email: EmailStr
    password: str = Field(min_length=6)

class UserOut(BaseModel):
    customer_id: int
    first_name: str
    last_name: str
    email: EmailStr
    role: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"