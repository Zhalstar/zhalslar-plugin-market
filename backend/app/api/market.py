"""AstrBot-compatible marketplace endpoints."""

from fastapi import APIRouter, Response

from ..dependencies import Database
from ..market import market_bytes, market_md5

router = APIRouter(tags=["AstrBot compatibility"])


@router.get("/market.json", include_in_schema=False)
def market_json(db: Database) -> Response:
    """Return the AstrBot-compatible marketplace JSON.

    Args:
        db: Open database session.

    Returns:
        Deterministic UTF-8 JSON response.
    """
    return Response(market_bytes(db), media_type="application/json")


@router.get("/market-md5.json", include_in_schema=False)
def market_fingerprint(db: Database) -> dict[str, str]:
    """Return the current AstrBot marketplace MD5 fingerprint.

    Args:
        db: Open database session.

    Returns:
        MD5 response object.
    """
    return {"md5": market_md5(db)}
