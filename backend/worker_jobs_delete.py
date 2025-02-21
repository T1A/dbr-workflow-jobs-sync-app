import os
from concurrent.futures import ThreadPoolExecutor
from databricks.sdk import WorkspaceClient
from backend.util.job_logger import setup_job_logger, log_exception

class JobDeleteTaskComponent:
    def __init__(self, delete_task_id: str, client: WorkspaceClient, temp_dir: str, job_statuses: list):
        self.delete_task_id = delete_task_id
        self.client = client
        self.temp_dir = temp_dir
        self.job_statuses = job_statuses
        
        self.logger, self.log_handler = setup_job_logger(f"{delete_task_id}")
        
        self.status = 'pending'
        self.output = 'Delete initialized'
        self.progress = {
            "deleted": 0,
            "failed_jobs": 0
        }
        
        self.num_threads = int(os.getenv("NUM_THREADS", "4"))
        
        self.existing_jobs = {job.settings.name: job for job in self.client.jobs.list()}
        
        # Only initialize status for jobs marked for deletion
        self.job_delete_statuses = {
            job_status["job_name"]: {
                "job_name": job_status["job_name"],
                "task_request": job_status,
                "delete_status": "pending",
                "error_message": None
            }
            for job_status in job_statuses
            if job_status['status'] == 'deleted'
        }

    def process_delete_task(self):
        self.status = 'running'
        self.output = 'Starting deletion...'
        
        try:
            # Filter jobs to process - only delete jobs that are marked for deletion
            jobs_to_process = [
                job_status for job_status in self.job_statuses 
                if job_status['status'] == 'deleted'
            ]

            # Sort jobs by name before processing
            jobs_to_process.sort(key=lambda x: x['job_name'])

            # Process jobs in parallel
            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                future_to_job = {
                    executor.submit(self.delete_single_job, job): job 
                    for job in jobs_to_process
                }
                
                for future in future_to_job:
                    job = future_to_job[future]
                    try:
                        success = future.result()
                        if success:
                            self.progress['deleted'] += 1
                        else:
                            self.progress['failed_jobs'] += 1
                    except Exception as e:
                        self.progress['failed_jobs'] += 1
                        log_exception(self.logger, f"Error deleting job {job['job_name']}", e)

            # Set final status
            if self.progress['failed_jobs'] > 0:
                self.status = 'completed_with_errors'
                self.output = f"Deletion completed with {self.progress['failed_jobs']} failures"
            else:
                self.status = 'completed'
                self.output = 'Deletion completed successfully'

        except Exception as e:
            self.status = 'failed'
            self.output = f'Deletion failed: {str(e)}'
            log_exception(self.logger, "Delete task failed", e)

    def _update_job_status(self, job_name: str, status: str, error_message: str = None):
        if job_name in self.job_delete_statuses:
            self.job_delete_statuses[job_name]["delete_status"] = status
            if error_message:
                self.job_delete_statuses[job_name]["error_message"] = error_message

    def delete_single_job(self, job_status: dict) -> bool:
        job_name = job_status['job_name']
        
        try:
            # Set status to in_progress when we actually start deleting
            self._update_job_status(job_name, "in_progress")
            
            if job_name in self.existing_jobs:
                existing_job = self.existing_jobs[job_name]
                self.client.jobs.delete(job_id=existing_job.job_id)
                self.logger.info(f"Deleted job: {job_name}")
                self._update_job_status(job_name, "completed")
                return True
            else:
                error_msg = f"Job {job_name} not found in workspace"
                self.logger.warning(error_msg)
                self._update_job_status(job_name, "error", error_msg)
                return False
            
        except Exception as e:
            error_msg = f"Failed to delete job: {str(e)}"
            if hasattr(e, 'response') and hasattr(e.response, 'json'):
                try:
                    error_details = e.response.json()
                    if 'error' in error_details:
                        error_msg = f"Failed to delete job: {error_details['error']}"
                    elif 'message' in error_details:
                        error_msg = f"Failed to delete job: {error_details['message']}"
                except:
                    pass  # If we can't parse the error response, stick with the original error message
            self.logger.error(f"Failed to delete job {job_name}: {str(e)}")
            self._update_job_status(job_name, "error", error_msg)
            return False 