from fastapi import APIRouter
from .api_workspace_info_router import router as workspace_info_router
from .api_export_router import router as export_router
from .api_validation_router import router as import_validation_router
from .api_import_router import router as import_router
from .api_delete_router import router as delete_router

# Create the main API router
router = APIRouter()

# Include all the modularized routers
router.include_router(workspace_info_router)
router.include_router(export_router)
router.include_router(import_validation_router)
router.include_router(import_router)
router.include_router(delete_router)
