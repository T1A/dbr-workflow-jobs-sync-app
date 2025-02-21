from fastapi import APIRouter, HTTPException, Depends
from threading import Thread
import uuid
import logging
from databricks.sdk import WorkspaceClient
import json

from backend.dependencies import get_workspace_client
from backend.schemas.tasks import ImportTaskRequest, ImportTaskResponse, ImportStatusResponse
from backend.task_manager import TaskManager
from backend.worker_jobs_import import JobImportTaskComponent

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

task_manager = TaskManager()


@router.post("/import/start", response_model=ImportTaskResponse)
async def start_import(
    request: ImportTaskRequest,
    client: WorkspaceClient = Depends(get_workspace_client)
):
    # Check for any existing running import tasks
    running_tasks = [task for task_id, task in task_manager.tasks.items() 
                    if isinstance(task, JobImportTaskComponent) and task.status == 'running']
    if running_tasks:
        logger.warning("Attempted to start new import while another import is running")
        raise HTTPException(
            status_code=409,
            detail="Another import task is currently running. Please wait for it to complete."
        )

    import_task_id = str(uuid.uuid4())
    logger.info(f"Starting new import task with ID: {import_task_id}, tempDir: {request.tempDir}")
    
    # Create import task component
    import_task = JobImportTaskComponent(
        import_task_id=import_task_id,
        client=client,
        temp_dir=request.tempDir,
        job_statuses=request.jobStatuses
    )
    
    # Add task to task manager
    task_manager.add_task(import_task_id, import_task)
    
    # Start processing in background thread
    Thread(target=import_task.process_import_task).start()
    
    return ImportTaskResponse(importTaskId=import_task_id)

@router.get("/import/{import_task_id}/status", response_model=ImportStatusResponse)
async def import_status(import_task_id: str):
    logger.debug(f"Status request for import task {import_task_id}")
    task = task_manager.get_task(import_task_id)
    if not task:
        logger.warning(f"Import task {import_task_id} not found")
        raise HTTPException(status_code=404, detail="Import task not found")
    
   # Transform dict to list and convert to camelCase for API response
    job_import_statuses = [
        {
            "jobName": status["job_name"],
            "taskRequest": status["task_request"],
            "importStatus": status["import_status"],
            "errorMessage": status.get("error_message")  # Use get() to safely handle missing error messages
        }
        for status in task.job_import_statuses.values()
    ]
    
    return ImportStatusResponse(
        status=task.status,
        output=task.output,
        progress=task.progress,
        jobImportStatuses=job_import_statuses,
        logRecords=task.log_handler.get_logs()
    )