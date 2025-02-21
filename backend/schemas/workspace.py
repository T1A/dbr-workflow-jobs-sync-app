from pydantic import BaseModel
from typing import Optional

class WorkspaceFilesInfo(BaseModel):
    workspace_last_modified: str
    json_files_count: int

class WorkspaceFolderResponse(BaseModel):
    workspace_git_folder: str
    databricks_host: str
    folder_id: int

class WorkflowJobsCount(BaseModel):
    workflow_jobs_count: int

class ComputeClusterMappingsResponse(BaseModel):
    compute_cluster_mappings: dict
    mappings_file_path: str

class ComputeClusterMappingsUpdateResponse(BaseModel):
    message: str 