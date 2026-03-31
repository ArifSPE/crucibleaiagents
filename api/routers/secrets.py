import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from utils import dependency as dependencies
from utils.rate_limit import limiter
from services.secret_service import (
    serialize_secret,
    list_secrets as svc_list_secrets,
    get_secret_or_404,
    create_or_update_secret,
    update_secret as svc_update_secret,
    delete_secret as svc_delete_secret,
)
from utils.logger import get_logger, log_event, log_exception

router = APIRouter()
LOGGER = get_logger("api.secrets")


class SecretUpsert(BaseModel):
    key_name: str
    value: str  # plaintext — encrypted before storage, never returned


@router.get("/packages/{package_id}/secrets")
def list_secrets(package_id: int):
    """List secret key names for a package. Values are never returned."""
    with dependencies.db_session() as db:
        secrets = svc_list_secrets(db, package_id)
        log_event(LOGGER, logging.INFO, "secrets.list", "Listed secret keys",
                  package_id=package_id, count=len(secrets))
        return JSONResponse(content=[serialize_secret(s) for s in secrets])


@router.get("/packages/{package_id}/secrets/{secret_id}")
def get_secret(package_id: int, secret_id: int):
    """Get secret metadata by ID. Value is never returned."""
    with dependencies.db_session() as db:
        secret = get_secret_or_404(db, package_id, secret_id)
        return JSONResponse(content=serialize_secret(secret))


@router.post("/packages/{package_id}/secrets")
@limiter.limit("60/minute")
def create_secret(request: Request, package_id: int, body: SecretUpsert):
    """Create a new secret. Value is encrypted before storage."""
    with dependencies.db_session() as db:
        secret, created, missing_secret_keys = create_or_update_secret(db, package_id, body.key_name, body.value)
        if not created:
            log_event(LOGGER, logging.INFO, "secret.updated", "Secret value updated",
                      secret_id=secret.id, package_id=package_id, key_name=body.key_name,
                      missing_secret_keys=missing_secret_keys)
            return JSONResponse(status_code=200, content=serialize_secret(secret))

        log_event(LOGGER, logging.INFO, "secret.created", "Secret created",
                  secret_id=secret.id, package_id=package_id, key_name=body.key_name,
                  missing_secret_keys=missing_secret_keys)
        return JSONResponse(status_code=201, content=serialize_secret(secret))


@router.put("/packages/{package_id}/secrets/{secret_id}")
@limiter.limit("60/minute")
def update_secret(request: Request, package_id: int, secret_id: int, body: SecretUpsert):
    """Update key name and/or value of an existing secret. Value is re-encrypted on update."""
    with dependencies.db_session() as db:
        secret, missing_secret_keys = svc_update_secret(db, package_id, secret_id, body.key_name, body.value)

        log_event(LOGGER, logging.INFO, "secret.updated", "Secret updated",
                  secret_id=secret_id, package_id=package_id, key_name=body.key_name,
                  missing_secret_keys=missing_secret_keys)
        return JSONResponse(content=serialize_secret(secret))


@router.delete("/packages/{package_id}/secrets/{secret_id}")
@limiter.limit("60/minute")
def delete_secret(request: Request, package_id: int, secret_id: int):
    """Delete a secret permanently."""
    with dependencies.db_session() as db:
        key_name, missing_secret_keys = svc_delete_secret(db, package_id, secret_id)

        log_event(LOGGER, logging.INFO, "secret.deleted", "Secret deleted",
                  secret_id=secret_id, package_id=package_id, key_name=key_name,
                  missing_secret_keys=missing_secret_keys)
        return JSONResponse(content={"deleted": True, "id": secret_id})
