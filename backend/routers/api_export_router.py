from fastapi import APIRouter, HTTPException, Depends
from threading import Thread
import uuid
import logging
from databricks.sdk import WorkspaceClient

from backend.dependencies import get_workspace_client
from backend.schemas.tasks import ExportTaskResponse, ExportStatusResponse
from backend.worker_jobs_export import export_task
from backend.task_manager import TaskManager

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

task_manager = TaskManager()

@router.post("/export/start", response_model=ExportTaskResponse)
async def start_export(client: WorkspaceClient = Depends(get_workspace_client)):
    # Check for any existing running export tasks
    running_tasks = [task for task_id, task in task_manager.tasks.items() 
                    if isinstance(task, dict) and task.get('type') == 'export' and task.get('status') == 'running']
    if running_tasks:
        logger.warning("Attempted to start new export while another export is running")
        raise HTTPException(
            status_code=409,
            detail="Another export task is currently running. Please wait for it to complete."
        )

    export_task_id = str(uuid.uuid4())
    logger.info(f"Starting new export task with ID: {export_task_id}")
    
    #TBD refactor to create ExportTaskComponent instance similarly to import tasks
    task_manager.add_task(export_task_id, {
        'type': 'export',
        'status': 'running',
        'output': 'Starting export process...\n',
        'progress': {
            'total_jobs': 0,
            'processed_jobs': 0,
            'exported_modified': 0,
            'exported_unchanged': 0,
            'failed_jobs': 0,
            'deleted_files': 0
        }
    })

    Thread(target=export_task, args=(export_task_id, client)).start()
    
    return ExportTaskResponse(exportTaskId=export_task_id)

@router.get("/export/{export_task_id}/status", response_model=ExportStatusResponse)
async def export_status(export_task_id: str):
    logger.debug(f"Status request for task {export_task_id}")
    task_info = task_manager.get_task(export_task_id)
    if not task_info:
        logger.warning(f"Export task {export_task_id} not found")
        raise HTTPException(status_code=404, detail="Export task not found")
    
    logger.debug(f"Returning status for task {export_task_id}: {task_info['status']}")
    return ExportStatusResponse(
        status=task_info["status"],
        output=task_info["output"],
        progress=task_info["progress"]
    ) 