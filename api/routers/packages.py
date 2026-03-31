import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from utils import dependency as dependencies
from utils.rate_limit import limiter

#from middleware.auth import _is_watcher_request
from services.package_service import (
    serialize_package,
    list_packages as svc_list_packages,
    get_package_or_404,
    register_package as svc_register_package,
)
from schemas.packages import PackageDisableUpdate, PackageRegisterRequest
from utils.logger import get_logger, log_event, log_exception

router = APIRouter()
LOGGER = get_logger("api.packages")

@router.get("/packages")
async def list_packages():
    LOGGER.info("Listing all packages")
    with dependencies.db_session() as db:
        pkgs = svc_list_packages(db)
        return JSONResponse(content=[serialize_package(pkg) for pkg in pkgs])
    
@router.get("/packages/{package_id}")
def get_package(package_id: int):
    LOGGER.info(f"Retrieving package with ID: {package_id}")
    with dependencies.db_session() as db:
        pkg = get_package_or_404(db, package_id)
        return JSONResponse(content=serialize_package(pkg))


@router.post("/packages/register")
@limiter.limit("30/minute")
def register_package(request: Request, payload: PackageRegisterRequest):
    """Register package metadata without uploading zip bytes."""
    with dependencies.db_session() as db:
        package, created, package_action, provisioned_secret_keys, missing_required_secret_keys, effective_schedule_enabled = svc_register_package(db, payload)

        if missing_required_secret_keys:
            log_event(
                LOGGER,
                logging.WARNING,
                "package.schedule_blocked_missing_secrets",
                "Schedule activation blocked until required secrets are populated",
                package_id=package.id,
                missing_secrets=sorted(set(missing_required_secret_keys)),
            )

        log_event(
            LOGGER,
            logging.INFO,
            "package.registered",
            "Package metadata registered",
            package_id=package.id,
            package_name=package.name,
            created=created,
            action=package_action,
            schedule_enabled=effective_schedule_enabled,
            schedule_type=package.schedule_type,
            secrets_count=len(payload.secret_keys or []),
            provisioned_secret_keys=provisioned_secret_keys,
        )

        return JSONResponse(
            content={
                "id": package.id,
                "name": package.name,
                "version": package.version,
                "created": created,
            }
        )
