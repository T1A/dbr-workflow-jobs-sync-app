from fastapi import APIRouter, HTTPException, Depends
from threading import Thread
import uuid
import logging
from databricks.sdk import WorkspaceClient

from backend.dependencies import get_workspace_client
from backend.schemas.tasks import ImportTaskResponse, ImportValidationStatus
from backend.worker_jobs_validate import JobimportValidationTaskComponent
from backend.task_manager import TaskManager

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

task_manager = TaskManager()

@router.post("/pre-import-validation/start", response_model=ImportTaskResponse)
async def start_import_validation(client: WorkspaceClient = Depends(get_workspace_client)):
    import_validation_task_id = str(uuid.uuid4())
    
    logger.info(f"Starting new import validation task with ID: {import_validation_task_id}")
    
    import_validation_task = JobimportValidationTaskComponent(import_validation_task_id, client)
    task_manager.add_task(import_validation_task_id, import_validation_task)
    
    Thread(target=import_validation_task.process_import_validation_task, args=()).start()
    
    return ImportTaskResponse(importTaskId=import_validation_task_id)

@router.get("/pre-import-validation/{import_task_id}/status", response_model=ImportValidationStatus)
async def import_status(import_task_id: str):
    logger.debug(f"Status request for import task {import_task_id}")
    task = task_manager.get_task(import_task_id)
    if not task:
        logger.warning(f"Import task {import_task_id} not found")
        raise HTTPException(status_code=404, detail="Import task not found")
    
    logger.debug(f"Returning status for import task {import_task_id}: {task.status}")
    return ImportValidationStatus(
        status=task.status,
        message=task.message,
        taskIssues=task.validation_task_issues,
        jobStatuses=task.job_validation_statuses,
        logRecords=task.log_handler.get_logs(),
        tempDir=task.temp_dir if task.temp_dir else None,
        progress=task.progress_stats
    ) 