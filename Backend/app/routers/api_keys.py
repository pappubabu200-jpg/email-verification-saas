# backend/app/routers/api_keys.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user
from backend.app.repositories.api_key_repository import ApiKeyRepository
from backend.app.schemas.api_key import ApiKeyCreate, ApiKeyResponse
from backend.app.models.api_key import ApiKey

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


# ---------------------------------------
# DB dependency
# ---------------------------------------
async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------
# POST /api-keys/create  — Create API key
# ---------------------------------------
@router.post("/create")
async def create_api_key(
    payload: ApiKeyCreate,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates a new API key.
    Returns:
    - raw_key (visible once)
    - key metadata
    """
    repo = ApiKeyRepository(db)

    # Generate raw + hashed key
    raw_key, key_obj = ApiKey.create_key(
        user_id=current_user.id,
        name=payload.name
    )

    # Save hashed key in DB
    saved = await repo.create(key_obj.__dict__)

    return {
        "raw_key": raw_key,  # only shown now
        "api_key": ApiKeyResponse.from_orm(saved)
    }


# ---------------------------------------
# GET /api-keys  — List user keys
# ---------------------------------------
@router.get("/", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = ApiKeyRepository(db)
    keys = await repo.get_user_keys(current_user.id)
    return [ApiKeyResponse.from_orm(k) for k in keys]


# ---------------------------------------
# DELETE /api-keys/{id}  — Delete API key
# ---------------------------------------
@router.delete("/{key_id}")
async def delete_api_key(
    key_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = ApiKeyRepository(db)
    key = await repo.get(key_id)

    if not key or key.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="API Key not found")

    await repo.delete(key)
    return {"deleted": True}


# ---------------------------------------
# POST /api-keys/{id}/rotate  — Rotate key
# ---------------------------------------
@router.post("/{key_id}/rotate")
async def rotate_api_key(
    key_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivates old key, generates a new raw key.
    Safe for production.
    """
    repo = ApiKeyRepository(db)
    key = await repo.get(key_id)

    if not key or key.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="API Key not found")

    # Generate new key
    raw_key, new_key_obj = ApiKey.create_key(
        user_id=current_user.id,
        name=key.name,
    )

    # Assign new hash
    key.key_hash = new_key_obj.key_hash
    key.used_today = 0  # reset usage
    await repo.update(key, {"key_hash": new_key_obj.key_hash})

    return {
        "rotated": True,
        "raw_key": raw_key  # show once
    }


# ---------------------------------------
# Activate / Deactivate an API Key
# ---------------------------------------

@router.post("/{key_id}/activate")
async def activate_api_key(
    key_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = ApiKeyRepository(db)
    key = await repo.get(key_id)

    if not key or key.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="API Key not found")

    updated = await repo.update(key, {"active": True})
    return ApiKeyResponse.from_orm(updated)


@router.post("/{key_id}/deactivate")
async def deactivate_api_key(
    key_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = ApiKeyRepository(db)
    key = await repo.get(key_id)

    if not key or key.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="API Key not found")

    updated = await repo.update(key, {"active": False})
    return ApiKeyResponse.from_orm(updated)
