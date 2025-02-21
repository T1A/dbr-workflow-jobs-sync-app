from fastapi import APIRouter, HTTPException, Depends
from threading import Thread
import uuid
import logging
from databricks.sdk import WorkspaceClient

from backend.dependencies import get_workspace_client
from backend.schemas.tasks import DeleteTaskRequest, DeleteTaskResponse, DeleteStatusResponse, JobDeleteStatus
from backend.task_manager import TaskManager
from backend.worker_jobs_delete import JobDeleteTaskComponent

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

task_manager = TaskManager()


@router.post("/delete/start", response_model=DeleteTaskResponse)
async def start_delete(
    request: DeleteTaskRequest,
    client: WorkspaceClient = Depends(get_workspace_client)
):
    # Check for any existing running delete tasks
    running_tasks = [task for task_id, task in task_manager.tasks.items() 
                    if isinstance(task, JobDeleteTaskComponent) and task.status == 'running']
    if running_tasks:
        logger.warning("Attempted to start new deletion while another deletion is running")
        raise HTTPException(
            status_code=409,
            detail="Another delete task is currently running. Please wait for it to complete."
        )

    delete_task_id = str(uuid.uuid4())
    logger.info(f"Starting new delete task with ID: {delete_task_id}, tempDir: {request.tempDir}")
    
    # Create delete task component
    delete_task = JobDeleteTaskComponent(
        delete_task_id=delete_task_id,
        client=client,
        temp_dir=request.tempDir,
        job_statuses=request.jobStatuses
    )
    
    # Add task to task manager
    task_manager.add_task(delete_task_id, delete_task)
    
    # Start processing in background thread
    Thread(target=delete_task.process_delete_task).start()
    
    return DeleteTaskResponse(deleteTaskId=delete_task_id)

@router.get("/delete/{delete_task_id}/status", response_model=DeleteStatusResponse)
async def delete_status(delete_task_id: str):
    logger.debug(f"Status request for delete task {delete_task_id}")
    task = task_manager.get_task(delete_task_id)
    if not task:
        logger.warning(f"Delete task {delete_task_id} not found")
        raise HTTPException(status_code=404, detail="Delete task not found")
    
    # Transform dict to list and convert to model instances
    job_delete_statuses = [
        JobDeleteStatus(
            jobName=status["job_name"],
            taskRequest=status["task_request"],
            deleteStatus=status["delete_status"],
            errorMessage=status.get("error_message")  # Use get() to safely handle missing error messages
        )
        for status in task.job_delete_statuses.values()
    ]
    
    return DeleteStatusResponse(
        status=task.status,
        output=task.output,
        progress=task.progress,
        jobDeleteStatuses=job_delete_statuses,
        logRecords=task.log_handler.get_logs()
    ) 