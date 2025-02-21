import json, json5  
import os, sys
from concurrent.futures import ThreadPoolExecutor
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import JobSettings, Task, NotebookTask
from backend.util.job_logger import setup_job_logger, log_exception
import random  

class JobImportTaskComponent:
    def __init__(self, import_task_id: str, client: WorkspaceClient, temp_dir: str, job_statuses: list):
        self.import_task_id = import_task_id
        self.client = client
        self.temp_dir = temp_dir
        self.job_statuses = job_statuses
        
        self.logger, self.log_handler = setup_job_logger(f"{import_task_id}")
        
        self.status = 'pending'
        self.output = 'Import initialized'
        self.progress = {
            "imported": 0,
            "skipped_unchanged": 0,
            "deleted": 0,
            "failed_jobs": 0
        }
        self.log_records = []
        
        self.num_threads = int(os.getenv("NUM_THREADS", "4"))
        
        self.existing_jobs = {job.settings.name: job for job in self.client.jobs.list()}
        
        self.job_import_statuses = {
            job_status["job_name"]: {
                "job_name": job_status["job_name"],
                "task_request": job_status,
                "import_status": "pending",
                "error_message": None
            }
            for job_status in job_statuses
        }

    def process_import_task(self):
        self.status = 'running'
        self.output = 'Starting import...'
        self.log_records = self.log_handler.get_logs()
        
        try:
            # Filter jobs to process
            jobs_to_process = []
            for job_status in self.job_statuses:
                if job_status['status'] in ['unchanged', 'error', 'deleted']:
                    self.progress['skipped_unchanged'] += 1
                    self._update_job_status(job_status['job_name'], "skipped")
                    continue
                if job_status['status'] in ['new', 'changed']:
                    jobs_to_process.append(job_status)

            # Sort jobs by name before processing
            jobs_to_process.sort(key=lambda x: x['job_name'])

            # Process jobs in parallel
            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                future_to_job = {
                    executor.submit(self.import_single_job, job, mode='update'): job 
                    for job in jobs_to_process
                }
                
                for future in future_to_job:
                    job = future_to_job[future]
                    try:
                        success = future.result()
                        if success:
                            self.progress['imported'] += 1
                        else:
                            self.progress['failed_jobs'] += 1
                    except Exception as e:
                        self.progress['failed_jobs'] += 1
                        log_exception(self.logger, f"Error importing job {job['job_name']}", e)

            # Set final status
            if self.progress['failed_jobs'] > 0:
                self.status = 'completed_with_errors'
                self.output = f"Import completed with {self.progress['failed_jobs']} failures"
            else:
                self.status = 'completed'
                self.output = 'Import completed successfully'

        except Exception as e:
            self.status = 'failed'
            self.output = f'Import failed: {str(e)}'
            log_exception(self.logger, "Import task failed", e)

    def _update_job_status(self, job_name: str, status: str, error_message: str = None):
        if job_name in self.job_import_statuses:
            self.job_import_statuses[job_name]["import_status"] = status
            if error_message:
                self.job_import_statuses[job_name]["error_message"] = error_message

    def import_single_job(self, job_status: dict, mode: str = 'update') -> bool:
        job_name = job_status['job_name']
        validated_job_path = os.path.join(self.temp_dir, "validated_jobs", f"{job_name}.json")
        
        try:
            # Set status to in_progress when we actually start importing
            self._update_job_status(job_name, "in_progress")
            
            # Load validated job definition
            with open(validated_job_path, 'r') as f:
                job_dict = json.load(f)
                
            if job_name in self.existing_jobs:
                # Update existing job
                existing_job = self.existing_jobs[job_name]
                job_settings = JobSettings.from_dict(job_dict['settings'])
                if mode == 'update':
                    self.client.jobs.reset(job_id=existing_job.job_id, new_settings=job_settings)
                    self.logger.info(f"Updated job: {job_name}")
            else:
                # Create new job
                job_settings = JobSettings.from_dict(job_dict['settings'])
                if mode == 'update':
                    self.client.jobs.create(**job_settings.__dict__)
                    self.logger.info(f"Created new job: {job_name}")
                
            self._update_job_status(job_name, "completed")
            return True
            
        except Exception as e:
            error_msg = f"Failed to import job: {str(e)}"
            if hasattr(e, 'response') and hasattr(e.response, 'json'):
                try:
                    error_details = e.response.json()
                    if 'error' in error_details:
                        error_msg = f"Failed to import job: {error_details['error']}"
                    elif 'message' in error_details:
                        error_msg = f"Failed to import job: {error_details['message']}"
                except:
                    pass  # If we can't parse the error response, stick with the original error message
            self.logger.error(f"Failed to import job {job_name}: {str(e)}")
            self._update_job_status(job_name, "error", error_msg)
            return False
