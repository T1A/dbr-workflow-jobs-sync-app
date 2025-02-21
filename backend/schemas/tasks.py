from pydantic import BaseModel
from typing import Dict, Any, Optional, List

class JobStatus(BaseModel):
    file_name: str
    job_name: str | None 
    status: str
    differences: list
    validation_issues: list

class ExportTaskProgress(BaseModel):
    total_jobs: int
    exported_modified: int
    exported_unchanged: int
    failed_jobs: int
    deleted_files: int

class ExportTaskResponse(BaseModel):
    exportTaskId: str

class ExportStatusResponse(BaseModel):
    status: str
    output: str
    progress: ExportTaskProgress

class ImportTaskResponse(BaseModel):
    importTaskId: str

class ImportValidationTaskResponse(BaseModel):
    importValidationTaskId: str

class ImportValidationProgress(BaseModel):
    total_items: int
    processed_items: int
    files_to_transfer: int
    files_transferred: int
    jobs_to_validate: int
    jobs_validated: int

class ImportValidationStatus(BaseModel):
    status: str
    message: str
    taskIssues: List[Dict[str, Any]]
    jobStatuses: List[Dict[str, Any]]
    logRecords: List[str]
    tempDir: Optional[str]
    progress: ImportValidationProgress

class ImportTaskRequest(BaseModel):
    jobStatuses: List[Dict[str, Any]] 
    tempDir: str

class JobImportStatus(BaseModel):
    jobName: str
    taskRequest: Dict[str, Any]
    importStatus: str
    errorMessage: Optional[str] = None

class ImportStatusResponse(BaseModel):
    status: str
    output: str
    progress: dict
    jobImportStatuses: List[JobImportStatus] = []
    logRecords: List[str] = []

class TaskProgress(BaseModel):
    imported: Optional[int] = 0
    skipped_unchanged: Optional[int] = 0
    deleted: Optional[int] = 0
    failed_jobs: Optional[int] = 0

class LogRecord(BaseModel):
    level: str
    message: str
    timestamp: str

class DeleteTaskRequest(BaseModel):
    tempDir: str
    jobStatuses: List[Dict[str, Any]]

class DeleteTaskResponse(BaseModel):
    deleteTaskId: str

class JobDeleteStatus(BaseModel):
    jobName: str
    taskRequest: Dict[str, Any]
    deleteStatus: str
    errorMessage: Optional[str] = None

class DeleteStatusResponse(BaseModel):
    status: str
    output: str
    progress: Optional[TaskProgress]
    jobDeleteStatuses: List[JobDeleteStatus] = []
    logRecords: List[str] = []