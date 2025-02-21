import json, os, sys
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat
import logging
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from backend.task_manager import TaskManager
from backend.util.compare_job_configurations import compare_job_configurations

logger = logging.getLogger(__name__)

task_manager = TaskManager()

def get_cluster_name_by_id(w, cluster_id):
    try:
        cluster = w.clusters.get(cluster_id=cluster_id)
        return cluster.cluster_name
    except:
        return None
    
def get_warehouse_name_by_id(w, warehouse_id):
    try:
        warehouse = w.warehouses.get(id=warehouse_id)
        return warehouse.name
    except:
        return None

def get_job_name_by_id(w, job_id):
    try:
        job = w.jobs.get(job_id=job_id)
        return job.settings.name
    except:
        return None


def replace_ids_with_names(job_dict, w):
    if 'tasks' in job_dict['settings']:
        for task in job_dict['settings']['tasks']:

            # Replace cluster IDs
            if 'existing_cluster_id' in task:
                cluster_name = get_cluster_name_by_id(w, task['existing_cluster_id'])
                if cluster_name:
                    task['existing_cluster_id'] = f"__CLUSTER__{cluster_name}__"
                else:
                    task['existing_cluster_id'] = f"__CLUSTER__unknown__"

            # Replace warehouse IDs in sql_task
            if 'sql_task' in task and 'warehouse_id' in task['sql_task']:
                warehouse_name = get_warehouse_name_by_id(w, task['sql_task']['warehouse_id'])
                if warehouse_name:
                    task['sql_task']['warehouse_id'] = f"__WAREHOUSE__{warehouse_name}__"
                else:
                    task['sql_task']['warehouse_id'] = f"__WAREHOUSE__unknown__"

            # Replace job IDs in run_job_task
            if 'run_job_task' in task and 'job_id' in task['run_job_task']:
                job_name = get_job_name_by_id(w, task['run_job_task']['job_id'])
                if job_name:
                    task['run_job_task']['job_id'] = f"__JOB__{job_name}__"
                else:
                    task['run_job_task']['job_id'] = f"__JOB__unknown__"
    
    return job_dict

def sanitize_job_name(name):
    return name

def export_job_configuration(client, job):
    """
    Export a single job configuration.
    Returns: (success, job_dict, message)
    """
    try:
        logger.info(f"Exporting job configuration for '{job.settings.name}'")
        job_object = client.jobs.get(job_id=job.job_id)
        job_dict = job_object.as_dict()
        
        # Replace IDs with names
        job_dict = replace_ids_with_names(job_dict, client)
        
        return True, job_dict, f"Exported job configuration for '{job.settings.name}'"
    
    except Exception as e:
        logger.error(f"Failed to export job configuration for '{job.settings.name}': {str(e)}", exc_info=True)
        return False, None, f"Failed to export job configuration for '{job.settings.name}': {str(e)}"


def upload_job_configuration(client, job_name, job_dict, workspace_folder):
    """
    Upload a job configuration to the Databricks workspace.
    Returns: (success, message, was_modified)
    """
    try:
        workspace_path = f'{workspace_folder}/{job_name}.json'
        new_content = json.dumps(job_dict, indent=2)
        
        # Check if file exists and compare contents
        try:
            logger.info(f"Downloading existing configuration for job '{job_name}'")
            with client.workspace.download(workspace_path) as file:
                existing_content = file.read().decode('utf-8')
            logger.info(f"Successfully downloaded existing configuration for job '{job_name}'")

            existing_job_dict = json.loads(existing_content)
            
            is_different, difference_details = compare_job_configurations(existing_job_dict, job_dict)
            if not is_different:
                logger.info(f"No changes detected for job '{job_name}'")
                return True, f"Job '{job_name}' is unchanged", False
            
            # Log the differences
            logger.info(f"Changes detected for job '{job_name}':\n{difference_details}")
                
        except Exception as e:
            logger.info(f"No existing configuration found for job '{job_name}' or error downloading: {str(e)}")
            # File doesn't exist or other error - proceed with upload
            pass

        # Upload to Databricks workspace
        logger.info(f"Uploading modified job configuration to workspace path: {workspace_path}")
        client.workspace.upload(
            path=workspace_path,
            content=new_content.encode('utf-8'),
            overwrite=True,
            format=ImportFormat.RAW
        )
        
        return True, f"Uploaded modified job '{job_name}' to {workspace_path}", True
    
    except Exception as e:
        logger.error(f"Failed to upload job '{job_name}': {str(e)}", exc_info=True)
        return False, f"Failed to upload job '{job_name}': {str(e)}", False

def export_single_job(client, job, workspace_folder):
    """
    Export a single job to the Databricks workspace.
    Returns: (export_success, upload_success, export_message, upload_message)
    """
    job_name = sanitize_job_name(job.settings.name)
    
    # Export the job configuration
    export_success, job_dict, export_message = export_job_configuration(client, job)
    
    # If export was successful, proceed to upload
    if export_success:
        upload_success, upload_message, was_modified = upload_job_configuration(client, job_name, job_dict, workspace_folder)
    else:
        upload_success, upload_message, was_modified = False, "Upload skipped due to export failure.", False
    
    return export_success, upload_success, export_message, upload_message


def export_task(export_task_id: str, client: WorkspaceClient):
    try:
        workspace_folder = os.getenv("WORKSPACE_GIT_FOLDER_PATH")

        export_task = task_manager.get_task(export_task_id)

        # Get list of all current jobs and their names
        jobs_list = list(client.jobs.list())
        current_job_files = {f"{sanitize_job_name(job.settings.name)}.json" for job in jobs_list}
        
        total_jobs = len(jobs_list)
        task_manager.update_task(export_task_id, progress={
            'total_jobs': total_jobs,
            'processed_jobs': 0,
            'exported_modified': 0,
            'exported_unchanged': 0,
            'failed_jobs': 0,
            'deleted_files': 0
        })
        export_task['output'] += f"Found {total_jobs} jobs to export\n"
        logger.info(f"Found {total_jobs} jobs to export for task {export_task_id}")

        def process_job(job, idx):
            export_success, job_dict, export_message = export_job_configuration(client, job)
            upload_success, upload_message, was_modified = False, "Upload skipped due to export failure.", False

            # Log export step
            export_status_message = f"[{idx}/{total_jobs}] {export_message}\n"
            export_task['output'] += export_status_message
            logger.info(f"Task {export_task_id}: {export_status_message.strip()}")

            if export_success:
                upload_success, upload_message, was_modified = upload_job_configuration(
                    client, sanitize_job_name(job.settings.name), job_dict, workspace_folder
                )

                # Log upload step
                upload_status_message = f"[{idx}/{total_jobs}] {upload_message}\n"
                export_task['output'] += upload_status_message
                logger.info(f"Task {export_task_id}: {upload_status_message.strip()}")

            # Update progress stats
            progress = export_task['progress']
            progress['processed_jobs'] += 1
            if export_success and upload_success:
                if was_modified:
                    progress['exported_modified'] += 1
                else:
                    progress['exported_unchanged'] += 1
            else:
                progress['failed_jobs'] += 1

        with ThreadPoolExecutor(max_workers=int(os.getenv("NUM_THREADS"))) as executor:
            futures = {executor.submit(process_job, job, idx): idx 
                        for idx, job in enumerate(jobs_list, 1)}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error processing job: {str(e)}", exc_info=True)

        # Delete orphaned JSON files for jobs that no longer exist in the workspace
        try:
            existing_files = [entry.path.split('/')[-1] 
                            for entry in client.workspace.list(workspace_folder)
                            if entry.path.endswith('.json')]
            
            files_to_delete = set(existing_files) - current_job_files
            
            for file_name in files_to_delete:
                file_path = f"{workspace_folder}/{file_name}"
                try:
                    client.workspace.delete(file_path)
                    export_task['progress']['deleted_files'] += 1
                    delete_message = f"Deleted orphaned job definition: {file_name}\n"
                    export_task['output'] += delete_message
                    logger.info(f"Task {export_task_id}: {delete_message.strip()}")
                except Exception as e:
                    error_msg = f"Failed to delete {file_name}: {str(e)}\n"
                    export_task['output'] += error_msg
                    logger.error(f"Task {export_task_id}: {error_msg.strip()}")

        except Exception as e:
            error_msg = f"Error during cleanup: {str(e)}\n"
            export_task['output'] += error_msg
            logger.error(f"Task {export_task_id}: {error_msg.strip()}")

        task_manager.update_task(export_task_id, task_type='export', status='completed')
        export_task['output'] += "Export completed successfully\n"
        logger.info(f"Task {export_task_id} completed successfully")

    except Exception as e:
        error_msg = f"Error: {str(e)}\n"
        task_manager.update_task(export_task_id, task_type='export', status='failed')
        export_task['output'] += error_msg
        logger.error(f"Task {export_task_id} failed with error: {str(e)}", exc_info=True)