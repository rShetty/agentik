"""FastAPI dependency helpers."""
from fastapi import Header, HTTPException, status


def get_company_id(x_company_id: str = Header(..., alias="X-Company-Id")) -> str:
    """Extract and validate the company ID from request headers.

    All agent endpoints are scoped to a company. Callers must send
    X-Company-Id with every request.
    """
    if not x_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Company-Id header is required",
        )
    return x_company_id
