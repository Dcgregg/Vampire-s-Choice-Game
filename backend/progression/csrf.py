"""Small explicit CSRF boundary for cookie-authenticated progression writes."""
from fastapi import HTTPException, Request

TRUSTED_CSRF_HEADER = "X-VC-Progression"
TRUSTED_CSRF_VALUE = "1"


def require_trusted_progression_header(request: Request) -> None:
    """Require a non-simple header so cross-site forms cannot mutate ledgers."""
    if request.headers.get(TRUSTED_CSRF_HEADER) != TRUSTED_CSRF_VALUE:
        raise HTTPException(
            status_code=403,
            detail={"error": "csrf_check_failed"},
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
