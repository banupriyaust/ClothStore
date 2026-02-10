from fastapi import FastAPI, HTTPException, Depends
from app.db import get_conn
from app.models import (
     ProductOut,
    UserCreate,
    UserOut,
    LoginIn,
    TokenOut,
    OrderCreate,
    OrderOut,
    OrderItemOut,
    
)


from app.security import hash_password, verify_password, create_access_token
from app.auth import get_current_user, require_admin



app = FastAPI(title="Clothing Store API")

@app.get("/products", response_model=list[ProductOut])
def list_products():
    sql = """
    SELECT
        p.product_id AS product_id,
        p.name AS product_name,
        c.name AS category_name,
        p.price,
        p.stock
    FROM products p
    JOIN categories c ON c.category_id = p.category_id
    ORDER BY p.product_id;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


@app.post("/orders", response_model=OrderOut)
def create_order(payload: OrderCreate, user=Depends(get_current_user)):
    user_id = user["customer_id"]
    """
    Creates:
      - an order row
      - one order_item row (for this assignment: one product per order request)
    Returns order + item + totals.
    Decreases products.stock by quantity.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:

            # 1) Lock product row, verify stock, get price & name
            cur.execute(
                """
                SELECT product_id, name, price, stock
                FROM products
                WHERE product_id = %s
                FOR UPDATE;
                """,
                (payload.product_id,),
            )
            product = cur.fetchone()
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")

            if product["stock"] < payload.quantity:
                raise HTTPException(status_code=400, detail="Insufficient stock")

            unit_price = float(product["price"])
            product_name = product["name"]

            # 2) Decrease stock
            cur.execute(
                """
                UPDATE products
                SET stock = stock - %s
                WHERE product_id = %s;
                """,
                (payload.quantity, payload.product_id),
            )

            # 3) Insert order
            cur.execute(
                """
                INSERT INTO orders (customer_id)
                VALUES (%s)
                RETURNING order_id;
                """,
                (user_id,),
            )
            order_id = cur.fetchone()["order_id"]

            # 4) Insert order item (one item per request)
            cur.execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                VALUES (%s, %s, %s, %s)
                RETURNING product_id, quantity, unit_price;
                """,
                (order_id, payload.product_id, payload.quantity, unit_price),
            )
            item_row = cur.fetchone()

            total_price = float(item_row["unit_price"]) * int(item_row["quantity"])

            item_out = OrderItemOut(
                product_id=item_row["product_id"],
                product_name=product_name,
                unit_price=float(item_row["unit_price"]),
                quantity=int(item_row["quantity"]),
                total_price=total_price,
            )

            return OrderOut(
                order_id=order_id,
                user_id=user_id,
                items=[item_out],
                order_total=total_price,
            )


@app.get("/statistics/users")
def stats_by_users(admin=Depends(require_admin)):
    """
    Example output per user:
      user_id, order_count, items_bought, money_spent
    Uses SQL aggregates + joins.
    """
    sql = """
    SELECT
        o.customer_id AS user_id,
        COUNT(DISTINCT o.order_id) AS order_count,
        COALESCE(SUM(oi.quantity), 0) AS items_bought,
        COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS money_spent
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    GROUP BY o.customer_id
    ORDER BY money_spent DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


@app.get("/statistics/products")
def stats_products(admin=Depends(require_admin)):
    """
    Example output per product:
      product_id, product_name, times_ordered, units_sold, turnover
    Uses SQL aggregates + joins.
    """
    sql = """
    SELECT
        p.product_id,
        p.name AS product_name,
        COUNT(oi.order_id) AS times_ordered,
        COALESCE(SUM(oi.quantity), 0) AS units_sold,
        COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS turnover
    FROM products p
    JOIN order_items oi ON oi.product_id = p.product_id
    GROUP BY p.product_id, p.name
    ORDER BY turnover DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

@app.post("/users", response_model=UserOut)
def register_user(payload: UserCreate):
    hashed = hash_password(payload.password)

    with get_conn() as conn:
        with conn.cursor() as cur:
            # email uniqueness check
            cur.execute("SELECT customer_id FROM customers WHERE email=%s;", (payload.email,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Email already registered")

            cur.execute(
                """
                INSERT INTO customers (first_name, last_name, email, password, role)
                VALUES (%s, %s, %s, %s, 'customer')
                RETURNING customer_id, first_name, last_name, email, role;
                """,
                (payload.first_name, payload.last_name, payload.email, hashed),
            )
            return cur.fetchone()
        
@app.post("/users/login", response_model=TokenOut)
def login(payload: LoginIn):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT customer_id, email, password, role FROM customers WHERE email=%s;",
                (payload.email,),
            )
            user = cur.fetchone()

    if not user or not user.get("password"):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(subject=user["email"], role=user["role"], user_id=user["customer_id"])
    return {"access_token": token, "token_type": "bearer"}

@app.get("/orders")
def list_my_orders(user=Depends(get_current_user)):
    sql = """
    SELECT
      o.order_id,
      o.customer_id AS user_id,
      o.created_at,
      oi.product_id,
      p.name AS product_name,
      oi.quantity,
      oi.unit_price,
      (oi.quantity * oi.unit_price) AS line_total
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    JOIN products p ON p.product_id = oi.product_id
    WHERE o.customer_id = %s
    ORDER BY o.created_at DESC, o.order_id DESC;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user["customer_id"],))
            return cur.fetchall()

@app.delete("/users/{id}")
def delete_user(id: int, admin=Depends(require_admin)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM customers WHERE id=%s RETURNING id;", (id,))
            deleted = cur.fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="User not found")
            return {"deleted_user_id": deleted["id"]}

