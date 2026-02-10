from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.db import get_conn
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)

def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if creds is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = creds.credentials
    try:
        payload = decode_token(token)
        customer_id = int(payload["uid"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                 """
                SELECT customer_id, first_name, last_name, email, role
                FROM customers
                WHERE customer_id = %s;
                """,
                (customer_id,),
            )
            user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user  # dict_row

def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
