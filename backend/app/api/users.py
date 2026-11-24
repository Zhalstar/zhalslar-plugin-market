"""Public publisher profiles and authenticated profile editing."""

from io import BytesIO

from fastapi import APIRouter, HTTPException, Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..dependencies import CurrentUser, Database
from ..market import plugin_response
from ..models import Plugin, User, new_id
from ..schemas import PublicUserResponse, UserResponse

router = APIRouter(prefix="/users", tags=["Profiles"])


class ProfileUpdate(BaseModel):
    """Public nickname editing payload."""

    display_name: str = Field(max_length=100)


def normalize_avatar(data: bytes) -> bytes:
    """Decode a bounded raster image and re-encode a small WebP without metadata."""
    with Image.open(BytesIO(data), formats=("PNG", "JPEG", "WEBP")) as image:
        if max(image.size) > 4096 or image.width * image.height > 8_000_000:
            raise ValueError("Avatar dimensions are too large")
        avatar = ImageOps.exif_transpose(image).convert("RGBA")
        avatar.thumbnail((256, 256), Image.Resampling.LANCZOS)
        output = BytesIO()
        avatar.save(output, format="WEBP", quality=85, exif=b"", icc_profile=b"")
        return output.getvalue()


@router.post("/me", response_model=UserResponse)
def edit_profile(payload: ProfileUpdate, user: CurrentUser, db: Database) -> User:
    """Update the signed-in user's public nickname."""
    user.display_name = payload.display_name.strip()
    db.commit()
    return user


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(request: Request, user: CurrentUser, db: Database) -> User:
    """Accept a bounded raster image as a raw request body."""
    if request.headers.get("content-type") not in {
        "image/png",
        "image/jpeg",
        "image/webp",
    }:
        raise HTTPException(status_code=415, detail="Use a PNG, JPEG, or WebP avatar")
    limit = get_settings().market.max_avatar_bytes
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail="Avatar exceeds size limit")
        body.extend(chunk)
    try:
        user.avatar = await run_in_threadpool(normalize_avatar, bytes(body))
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail="Invalid avatar image") from exc
    user.avatar_revision = new_id()
    db.commit()
    return user


@router.delete("/me/avatar", response_model=UserResponse)
def remove_avatar(user: CurrentUser, db: Database) -> User:
    """Remove the signed-in user's current avatar."""
    user.avatar = None
    user.avatar_revision = None
    db.commit()
    return user


@router.get("/{user_id}/avatar", include_in_schema=False)
def get_avatar(user_id: str, db: Database) -> Response:
    """Return the current avatar only for an active public profile."""
    user = db.get(User, user_id)
    if user is None or not user.is_active or not user.avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return Response(
        user.avatar,
        media_type="image/webp",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=300",
        },
    )


@router.get("/{user_id}", response_model=PublicUserResponse)
def get_profile(user_id: str, db: Database) -> PublicUserResponse:
    """List the public profile fields and only its published plugins."""
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Profile not found")
    plugins = db.scalars(
        select(Plugin)
        .where(
            Plugin.owner_id == user_id,
            Plugin.status == "published",
        )
        .order_by(Plugin.updated_at.desc())
    ).all()
    return PublicUserResponse(
        id=user.id,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        plugins=[plugin_response(plugin) for plugin in plugins],
    )
