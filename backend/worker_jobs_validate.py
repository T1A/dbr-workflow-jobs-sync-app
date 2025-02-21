import json  
import os, sys
import logging
import tempfile 
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import Job, JobSettings, Task, NotebookTask
from databricks.sdk.service.workspace import ImportFormat

from backend.resource_name_mappings import RESOURCE_NAME_MAPPINGS_FILE_PATH, get_resource_name_mappings
from backend.util.job_logger import setup_job_logger, log_exception
from backend.util.compare_job_configurations import compare_job_configurations
from backend.util.dbr_workspace_utils import get_all_clusters_and_warehouses

class JobimportValidationTaskComponent:

    def __init__(self, import_task_id: str, client: WorkspaceClient):
        self.import_task_id = import_task_id
        self.client = client

        self.logger, self.log_handler = setup_job_logger(f"{import_task_id}")

        self.status = 'pending'
        self.message = ''

        self.validation_task_issues = []
        self.job_validation_statuses = [] 

        self.num_threads = int(os.getenv("NUM_THREADS", "4"))

        self.progress_stats = {
            'total_items': 0,
            'processed_items': 0,
            'files_to_transfer': 0,
            'files_transferred': 0,
            'jobs_to_validate': 0,
            'jobs_validated': 0
        }

    def download_job_definition_files(self, workspace_git_folder: str, temp_dir: str) -> list:
        """Download a all json file from workspace folder to temp_dir"""

        self.logger.info("Transferring job definition json files from Workspace to local folder...")
        successful_downloads = []

        # Check if workspace folder exists
        try:
            self.client.workspace.get_status(workspace_git_folder)
        except Exception as e:
            raise ValueError(f"Folder not found in workspace: {workspace_git_folder}")

        # Get list of files to process
        entries = list(self.client.workspace.list(workspace_git_folder))
        json_files = [entry for entry in entries if entry.path.endswith('.json')]
        
        if not json_files:
            raise ValueError(f"No .json files found in workspace folder: {workspace_git_folder}")

        self.logger.info(f"Using {self.num_threads} threads for parallel processing...")

        def download_single_file(file_name, temp_dir: str) -> tuple[str, str, bool]:
                
            local_path = os.path.join(temp_dir, os.path.basename(file_name.path))
            filename = os.path.basename(file_name.path)
            
            try:
                with self.client.workspace.download(file_name.path) as file:
                    with open(local_path, 'wb') as f:
                        f.write(file.read())
                # Update progress
                self.progress_stats['files_transferred'] += 1
                self.progress_stats['processed_items'] += 1
                return filename, local_path, True
            except Exception as e:
                self.validation_task_issues.append({
                    "file": filename,
                    "issue": f"Error during transferring from workspace folder: {str(e)}",
                    'level': 'Error'
                })
                log_exception(self.logger, f"Error transferring {filename}", e)
                return filename, None, False
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            future_to_entry = {
                executor.submit(download_single_file, entry, temp_dir): entry
                for entry in json_files
            }
            
            for future in future_to_entry:
                entry = future_to_entry[future]
                try:
                    filename, local_path, success = future.result()
                    if success:
                        successful_downloads.append((filename, local_path))
                        self.logger.info( f"Transferred {filename}")
                    else:
                        self.validation_task_issues.append({
                            "file": os.path.basename(entry.path),
                            "issue": "Failed to transfer file from workspace folder",
                            'level': 'Error'
                        })
                        self.logger.info( f"Failed to transfer {os.path.basename(entry.path)}")
                except Exception as e:
                    self.validation_task_issues.append({
                        "file": os.path.basename(entry.path),
                        "issue": f"Error during transferring from workspace folder: {str(e)}",
                        'level': 'Error'
                    })
                    log_exception(self.logger, f"Error transferring {os.path.basename(entry.path)}", e)
        
        if not successful_downloads:
            raise ValueError("No files were successfully downloaded")
        
        return successful_downloads

    def validate_single_job(self,
                        json_file_basename: str, local_file_path: str, 
                        resource_name_mappings: dict, all_clusters_dict: dict, all_warehouses_dict: dict,
                        all_importing_jobs_list: set, all_existing_jobs_dict: dict) -> list:
        """Validate a single job definition file and return any validation issues"""

        validation_issues = []
        
        # Sets to track unique resource validation issues
        cluster_issues = set()
        warehouse_issues = set()
        job_ref_issues = set()
        run_as_issues = set()

        job_status = {
            'file_name': json_file_basename,
            'job_name': None,
            'status': 'unknown',
            'differences': [],
            'validation_issues': []
        }
        
        try:
            with open(local_file_path, 'r') as f:
                importing_job_dict = json.load(f)

            #Job name from the definition file content (more reliable then the file name)
            job_name = importing_job_dict.get("settings", {}).get("name")
            job_status['job_name'] = job_name
                
            # Basic structure validation
            if "settings" not in importing_job_dict:
                validation_issues.append({
                    "file": json_file_basename,
                    "issue": "Missing required 'settings' attribute"
                })
                job_status['status'] = 'error'
                job_status['validation_issues'] = validation_issues
                return job_status
                
            settings = importing_job_dict["settings"]
            
            # Handle run_as_user_name if present at top level
            if 'run_as_user_name' in importing_job_dict:
                if 'settings' not in importing_job_dict:
                    importing_job_dict['settings'] = {}
                importing_job_dict['settings']['run_as'] = {
                    'user_name': importing_job_dict['run_as_user_name']
                }
                
            # Handle run_as mappings
            if 'run_as' in settings:
                run_as = settings['run_as']
                run_as_mappings = resource_name_mappings.get("run_as_mappings", {})
                
                # Get original user or service principal
                original_user = run_as.get('user_name')
                original_sp = run_as.get('service_principal_name')
                original_identity = original_user or original_sp
                
                if original_identity:
                    # Try to find specific mapping for the identity, fall back to default
                    mapping = run_as_mappings.get(original_identity) or run_as_mappings.get('default')
                    
                    if mapping:
                        # Validate mapping format
                        if not isinstance(mapping, dict) or not any(k in mapping for k in ['user_name', 'service_principal_name']):
                            run_as_issues.add(f"Invalid {'default ' if mapping == run_as_mappings.get('default') else ''}mapping format for RunAs identity '{original_identity}'")
                        else:
                            # Apply the mapping
                            mapped_identity = mapping.get('user_name') or mapping.get('service_principal_name')
                            settings['run_as'] = mapping
                            
                            # Update legacy run_as_user_name if present
                            if 'run_as_user_name' in importing_job_dict:
                                importing_job_dict['run_as_user_name'] = mapped_identity
                                self.logger.info(f"Job '{job_name}': Updated legacy run_as_user_name to '{mapped_identity}'")
                                
                            mapping_type = 'default' if mapping == run_as_mappings.get('default') else 'specific'
                            self.logger.info(f"Job '{job_name}': RunAs identity '{original_identity}' mapped to {mapping_type} mapping {mapping}")
                    else:
                        # Keep original identity but log it
                        self.logger.info(f"Job '{job_name}': Using original RunAs identity '{original_identity}' (no mapping found)")


            if "name" not in settings:
                validation_issues.append({
                    "file": json_file_basename,
                    "issue": "Missing required 'name' attribute in settings"
                })
            
            if "tasks" not in settings:
                validation_issues.append({
                    "file": json_file_basename,
                    "issue": "Missing required 'tasks' attribute in settings"
                })
                job_status['status'] = 'error'
                job_status['validation_issues'] = validation_issues
                return job_status
                
            # Tasks validation
            tasks = settings["tasks"]
            if not isinstance(tasks, list) or not tasks:
                validation_issues.append({
                    "file": json_file_basename,
                    "issue": "Tasks must be a non-empty list"
                })
                job_status['status'] = 'error'
                job_status['validation_issues'] = validation_issues
                return job_status
                
            for task_idx, task in enumerate(tasks):
                # Task key validation
                if "task_key" not in task:
                    validation_issues.append({
                        "file": json_file_basename,
                        "issue": f"Task at index {task_idx} missing required 'task_key'"
                    })
                
                # Cluster, Warehouse, Job references validation and resolution

                if "existing_cluster_id" in task:
                    cluster_id = task["existing_cluster_id"]
                    if isinstance(cluster_id, str) and cluster_id.startswith("__CLUSTER__"):

                        # Remove the __CLUSTER__ prefix
                        cluster_name = cluster_id.replace("__CLUSTER__", "").replace("__", "")

                        # Apply cluster name mappings
                        cluster_name = resource_name_mappings.get("compute_name_mappings", {}).get("cluster_name_mappings", {}).get(cluster_name, cluster_name)

                        # Identify Cluster ID from the name
                        cluster_id = all_clusters_dict.get(cluster_name, None)
                        if not cluster_id:
                            cluster_issues.add(f"Cluster '{cluster_name}' does not exist in this workspace")
                            continue

                        task["existing_cluster_id"] = cluster_id
                
                if "sql_task" in task and "warehouse_id" in task["sql_task"]:
                    warehouse_id = task["sql_task"]["warehouse_id"]
                    if isinstance(warehouse_id, str) and warehouse_id.startswith("__WAREHOUSE__"):
                        # Remove the __WAREHOUSE__ prefix
                        warehouse_name = warehouse_id.replace("__WAREHOUSE__", "").replace("__", "")

                        # Apply warehouse name mappings
                        warehouse_name = resource_name_mappings.get("compute_name_mappings", {}).get("warehouse_name_mappings", {}).get(warehouse_name, warehouse_name)

                        # Identify Warehouse ID from the name
                        warehouse_id = all_warehouses_dict.get(warehouse_name, None)
                        if not warehouse_id:
                            warehouse_issues.add(f"Warehouse '{warehouse_name}' does not exist in this workspace")
                            continue

                        task["sql_task"]["warehouse_id"] = warehouse_id
                
                # Job reference validation
                if "run_job_task" in task and "job_id" in task["run_job_task"]:
                    job_ref = task["run_job_task"]["job_id"]
                    if isinstance(job_ref, str) and job_ref.startswith("__JOB__"):

                        referenced_job_name = job_ref.replace("__JOB__", "").replace("__", "")
                       
                        job_ref_id = all_existing_jobs_dict.get(referenced_job_name, {}).get("job_id", None)
                        if not job_ref_id:
                            job_ref_issues.add(f"Referenced job '{referenced_job_name}' not found in this workspace")
                            continue

                        task["run_job_task"]["job_id"] = job_ref_id

            # Compare with existing workflow Job object (if present)
            if job_name in all_existing_jobs_dict.keys():
                existing_job = all_existing_jobs_dict[job_name]
                is_different, differences = compare_job_configurations(
                    existing_job, 
                    importing_job_dict
                )

                if is_different:
                    job_status['status'] = 'changed'
                    job_status['differences'] = differences
                else:
                    job_status['status'] = 'unchanged'
            else:
                job_status['status'] = 'new'

            # Persist updated job config to a new json file

            validated_jobs_dir = os.path.join(self.temp_dir, "validated_jobs")
            os.makedirs(validated_jobs_dir, exist_ok=True)
            
            updated_job_config_path = os.path.join(validated_jobs_dir, f"{job_name}.json")
            self.logger.info(f"Persisting updated job config to {updated_job_config_path}")
            with open(updated_job_config_path, 'w') as f:
                if ("t1a-job-v2-KTO_KANDIDAAT_BVV" in json_file_basename):
                    pass

                json.dump(importing_job_dict, f, indent=4)

            # Add deduplicated issues (from the set) to validation_issues
            for issue in cluster_issues:
                validation_issues.append({
                    "file": json_file_basename,
                    "issue": issue,
                    "type": "cluster_reference"
                })
                job_status['status'] = 'error'
                
            for issue in warehouse_issues:
                validation_issues.append({
                    "file": json_file_basename,
                    "issue": issue,
                    "type": "warehouse_reference"
                })
                job_status['status'] = 'error'
                
            for issue in job_ref_issues:
                validation_issues.append({
                    "file": json_file_basename,
                    "issue": issue,
                    "type": "job_reference"
                })
                job_status['status'] = 'error'

            # Add run_as validation issues
            for issue in run_as_issues:
                validation_issues.append({
                    "file": json_file_basename,
                    "issue": issue,
                    "type": "run_as_reference"
                })
                job_status['status'] = 'error'

        except Exception as e:
            validation_issues.append({
                "file": json_file_basename,
                "issue": f"Validation error: {str(e)}",
                "type": "validation_error"
            })
            job_status['status'] = 'error'
            job_status['validation_issues'] = validation_issues
            
            log_exception(self.logger, f"Error validating {json_file_basename}", e)

        job_status['validation_issues'] = validation_issues
            
        return job_status
        
    def get_all_jobs(self) -> List[Job]:
        """Get list of all jobs in the workspace"""
        try:
            self.logger.info("Getting list of all jobs in workspace...")
            return list(self.client.jobs.list())
        except Exception as e:
            self.logger.error(f"Failed to get jobs list: {str(e)}")
            raise

    def download_job_definition(self, job: Job) -> Optional[Tuple[str, dict]]:
        """Download full job definition for a single job"""
        try:
            self.logger.info(f"Downloading current-state job definition '{job.settings.name}'...")
            job_full = self.client.jobs.get(job_id=job.job_id).as_dict()
            return job.settings.name, job_full
        except Exception as e:
            self.logger.error(f"Failed to download job '{job.settings.name}': {str(e)}")
            return None

    def get_all_jobs_full(self, jobs_list: Optional[List[Job]] = None) -> dict:
        """Download all job definitions in parallel"""
        if jobs_list is None:
            jobs_list = self.get_all_jobs()
        
        all_jobs = {}
        
        self.logger.info(f"Downloading {len(jobs_list)} job definitions...")
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            future_to_job = {
                executor.submit(self.download_job_definition, job): job 
                for job in jobs_list
            }
            
            for future in as_completed(future_to_job):
                result = future.result()
                if result:
                    job_name, job_full = result
                    all_jobs[job_name] = job_full
                    # Update progress as each job is downloaded
                    self.progress_stats['jobs_validated'] += 1
                    self.progress_stats['processed_items'] += 1
                    self.logger.debug(f"Downloaded job definition for '{job_name}' ({self.progress_stats['jobs_validated']}/{self.progress_stats['jobs_to_validate']})")
        
        return all_jobs

    def process_import_validation_task(self):
        self.status = 'in_progress'
        self.message = 'Validation Started...'

        try:
            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp()
            self.logger.info(f"Temporary local directory: {self.temp_dir}")
            
            workspace_git_folder = os.getenv("WORKSPACE_GIT_FOLDER_PATH")
            if not workspace_git_folder:
                raise ValueError("WORKSPACE_GIT_FOLDER_PATH environment variable is not set")
                
            self.logger.info(f"Using workspace folder: {workspace_git_folder}")
                    
            # Get list of files and jobs upfront
            entries = list(self.client.workspace.list(workspace_git_folder))
            json_files = [entry for entry in entries if entry.path.endswith('.json')]
            
            if not json_files:
                raise ValueError(f"No .json files found in workspace folder: {workspace_git_folder}")

            # Get all jobs early to know total count and reuse later
            all_jobs_list = self.get_all_jobs()
            
            # Set initial progress stats with actual totals
            num_files = len(json_files)
            num_jobs = len(all_jobs_list)
            self.progress_stats = {
                'files_to_transfer': num_files,
                'files_transferred': 0,
                'jobs_to_validate': num_jobs,
                'jobs_validated': 0,
                'total_items': num_files + num_jobs,
                'processed_items': 0
            }
            self.logger.info(f"Found {num_files} files and {num_jobs} jobs to process")
            
            # Load compute cluster mappings
            self.logger.info(f"Loading compute resource mappings from {RESOURCE_NAME_MAPPINGS_FILE_PATH}...")
            resource_name_mappings = get_resource_name_mappings(self.client)
            if not resource_name_mappings:
                warning = {
                    'issue': "No compute resource mappings found. Some jobs may fail to import if clusters or warehouses with exact original names do not exist in this workspace.",
                    'file': None,
                    'level': 'warning'
                }
                self.validation_task_issues.append(warning)
                self.logger.info( f"Warning: {warning['issue']}")
            
        
            # Phase 1: Download of JSON files from workspace folder
            job_definition_files = self.download_job_definition_files(workspace_git_folder, self.temp_dir)
            
            # Collect all job names from the downloaded files
            all_importing_job_names = set()
            for json_file_basename, local_file_path in job_definition_files:
                try:
                    with open(local_file_path, 'r') as f:
                        job_config = json.load(f)
                        job_name = job_config.get("settings", {}).get("name")
                        if job_name:
                            all_importing_job_names.add(job_name)
                except Exception as e:
                    self.validation_task_issues.append({
                        "file": json_file_basename,
                        "issue": f"Error reading job name from file: {str(e)}",
                        "level": "Error"
                    })
                    self.logger.error(f"Error reading job name from {json_file_basename}: {str(e)}")
            
            # Cache compute resources mapping file
            self.logger.info( "Getting compute resources definitions (clusters and warehouses)...")
            all_clusters_dict, all_warehouses_dict = get_all_clusters_and_warehouses(self.client)

            # Phase 2: Download all existing job definitions (for comparison)
            self.logger.info("Downloading existing jobs definitions for comparison (in parallel)...")
            all_existing_jobs_dict = self.get_all_jobs_full(all_jobs_list)  # Pass the cached list

            # Phase 3: Validation of JSON files and comparison with existing job definitions
            self.logger.info("Validating job definitions (in parallel)...")
            
            future_to_file = {}
            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                # Submit each job for validation
                for json_file_basename, local_file_path in job_definition_files:
                    future = executor.submit(
                        self.validate_single_job,
                        json_file_basename=json_file_basename,
                        local_file_path=local_file_path,
                        resource_name_mappings=resource_name_mappings,
                        all_clusters_dict=all_clusters_dict,
                        all_warehouses_dict=all_warehouses_dict,
                        all_importing_jobs_list=all_importing_job_names,
                        all_existing_jobs_dict=all_existing_jobs_dict
                    )
                    future_to_file[future] = json_file_basename  # Store the basename instead of path
                
                # Process results as they arrive
                for future in future_to_file:
                    filename = future_to_file[future]  # Get filename from the dictionary
                    try:
                        job_status = future.result()
                        self.job_validation_statuses.append(job_status)
                        self.logger.info(f"Completed validation for {filename}, status: {job_status['status']}")
                    except Exception as e:
                        self.validation_task_issues.append({
                            "file": filename,
                            "issue": f"Validation for {filename} has failed with an error."
                        })
                        log_exception(self.logger, f"Error validating {filename}", e)
            
            # Check for deleted jobs
            deleted_jobs = [
                {
                    'job_name': existing_job_name,
                    'status': 'deleted',
                    'file': None,
                    'differences': []
                }
                for existing_job_name in all_existing_jobs_dict.keys()
                if existing_job_name not in all_importing_job_names
            ]

            self.job_validation_statuses.extend(deleted_jobs)

            # Check if any jobs had validation errors
            has_errors = any(status.get('status') == 'error' for status in self.job_validation_statuses)
            has_changed_jobd = any(status.get('status') in ('new', 'changed', 'deleted') for status in self.job_validation_statuses)
            has_unchanged_jobs = any(status.get('status') == 'unchanged' for status in self.job_validation_statuses)

            if has_errors:
                if has_changed_jobd:
                    self.status = 'completed_with_errors'
                    self.message = 'Validation completed. Some jobs had validation errors and will not be imported.'
                elif not has_changed_jobd and has_unchanged_jobs:
                    self.status = 'completed_no_changes'
                    self.message = 'Validation completed. Some jobs had validation errors. No changes detected.'
                else: 
                    self.status = 'failed'
                    self.message = 'Validation Failed. No jobs were validated successfully.'
            
            else:
                if has_changed_jobd:
                    self.status = 'completed'
                    self.message = 'Validation completed. Ready to import changed jobs.'
                elif not has_changed_jobd and has_unchanged_jobs:
                    self.status = 'completed_no_changes'
                    self.message = 'Validation completed. No job changes detected.'
                else:
                    self.status = 'completed_no_changes'
                    self.message =  'Validation completed. No job were detected or processed.'
                                
            self.logger.info(f"Validation Task {self.import_task_id} completed with status: {self.status}")
            
        except Exception as e:
            self.logger.error(f"Validation Task {self.import_task_id} failed with Exception: {str(e)}", exc_info=True)

            self.status = 'failed'
            self.message = f'Validation Failed: {str(e)}'

