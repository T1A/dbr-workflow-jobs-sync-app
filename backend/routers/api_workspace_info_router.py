from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime
import os
import logging
import time
from databricks.sdk import WorkspaceClient
from typing import Dict
from enum import Enum
from pydantic import BaseModel
import asyncio

from backend.dependencies import get_workspace_client
from backend.schemas.workspace import WorkspaceFilesInfo, WorkspaceFolderResponse, WorkflowJobsCount, ComputeClusterMappingsResponse, ComputeClusterMappingsUpdateResponse
from backend.resource_name_mappings import (
    RESOURCE_NAME_MAPPINGS_FILE_PATH,
    get_resource_name_mappings,
    update_resource_name_mappings
)

router = APIRouter(prefix="/api/workspace-info")
logger = logging.getLogger(__name__)

databricks_semaphore = asyncio.Semaphore(int(os.getenv("NUM_THREADS", "1")))

class AppMode(str, Enum):
    EXPORT = "Export"
    IMPORT = "Import"
    BOTH = "Both"

    @classmethod
    def _missing_(cls, value):
        # Handle case-insensitive lookup
        if isinstance(value, str):
            upper_value = value.upper()
            for member in cls:
                if member.name.upper() == upper_value:
                    return member
        return None

class AppModeResponse(BaseModel):
    mode: AppMode

@router.get("/folder", response_model=WorkspaceFolderResponse)
async def get_workspace_folder(client: WorkspaceClient = Depends(get_workspace_client)):
    async with databricks_semaphore:
        workspace_git_folder = os.getenv("WORKSPACE_GIT_FOLDER_PATH")
        databricks_host = os.getenv("DATABRICKS_HOST")
        
        try:
            folder_info = await asyncio.to_thread(client.workspace.get_status, workspace_git_folder)
            folder_id = folder_info.object_id
            
            return WorkspaceFolderResponse(
                workspace_git_folder=workspace_git_folder,
                databricks_host=databricks_host,
                folder_id=folder_id
            )
        except Exception as e:
            logger.error(f"Error getting folder info: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error getting folder info: {str(e)}")

@router.get("/files", response_model=WorkspaceFilesInfo)
async def get_workspace_files_info(client: WorkspaceClient = Depends(get_workspace_client)):
    async with databricks_semaphore:
        workspace_git_folder = os.getenv("WORKSPACE_GIT_FOLDER_PATH")
        try:
            directory_contents = await asyncio.to_thread(lambda: list(client.workspace.list(workspace_git_folder)))
            
            workspace_last_modified = max(
                (entry.modified_at for entry in directory_contents if entry.modified_at is not None),
                default=None
            )
            json_files = sum(1 for entry in directory_contents if entry.path.endswith('.json'))
            
            if workspace_last_modified:
                workspace_last_modified = datetime.fromtimestamp(workspace_last_modified / 1000)
                workspace_last_modified_str = workspace_last_modified.strftime("%Y-%m-%d %H:%M:%S")
            else:
                workspace_last_modified_str = "No files found"
                
            return WorkspaceFilesInfo(
                workspace_last_modified=workspace_last_modified_str,
                json_files_count=json_files
            )
        except Exception as e:
            logger.error(f"Error fetching workspace files info: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error fetching workspace files info: {str(e)}")

@router.get("/jobs-count", response_model=WorkflowJobsCount)
async def get_workflow_jobs_count(client: WorkspaceClient = Depends(get_workspace_client)):
    async with databricks_semaphore:
        try:
            jobs = await asyncio.to_thread(lambda: list(client.jobs.list()))
            jobs_count = len(jobs)
            return WorkflowJobsCount(workflow_jobs_count=jobs_count)
        except Exception as e:
            logger.error(f"Error counting workflow jobs: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error counting workflow jobs: {str(e)}")

@router.get("/compute-cluster-mappings", response_model=ComputeClusterMappingsResponse)
def get_compute_cluster_mappings(client: WorkspaceClient = Depends(get_workspace_client)):
    try:
        mappings = get_resource_name_mappings(client)
        return ComputeClusterMappingsResponse(
            compute_cluster_mappings=mappings,
            mappings_file_path=RESOURCE_NAME_MAPPINGS_FILE_PATH
        )
    except Exception as e:
        logger.error(f"Error getting compute cluster mappings: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/compute-cluster-mappings", response_model=ComputeClusterMappingsUpdateResponse)
def update_compute_cluster_mappings(
    mappings: Dict = Body(...),
    client: WorkspaceClient = Depends(get_workspace_client)
):
    update_resource_name_mappings(client, mappings)
    return ComputeClusterMappingsUpdateResponse(message="Compute cluster mappings updated successfully")

@router.get("/app-mode", response_model=AppModeResponse)
def get_app_mode():
    mode = os.getenv("APP_MODE", "Both")
    try:
        app_mode = AppMode(mode)
    except ValueError:
        logger.warning(f"Invalid APP_MODE value: {mode}. Defaulting to 'Both'")
        app_mode = AppMode.BOTH
    
    return AppModeResponse(mode=app_mode) 