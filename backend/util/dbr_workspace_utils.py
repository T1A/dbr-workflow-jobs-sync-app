from typing import List, Dict
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import Job, JobSettings, Task, NotebookTask
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)
    

def get_cluster_id_by_name(client: WorkspaceClient, cluster_name, name_mappings):
    """Get cluster ID from its name"""
    clusters = list(client.clusters.list())

    target_name = name_mappings.get(cluster_name, cluster_name)
    
    for cluster in clusters:
        if cluster.cluster_name == target_name:
            return cluster.cluster_id
        
    raise ValueError(f"Cluster not found: {target_name}")

def get_warehouse_id_by_name(client: WorkspaceClient, warehouse_name, name_mappings):
    """Get warehouse ID from its name"""
    warehouses = list(client.warehouses.list())
    target_name = name_mappings.get(warehouse_name, warehouse_name)
    
    for warehouse in warehouses:
        if warehouse.name == target_name:
            return warehouse.id
    raise ValueError(f"Warehouse not found: {target_name}")

def get_job_id_by_name(client: WorkspaceClient, job_name):
    """Get job ID from its name"""
    for job in client.jobs.list():
        if job.settings.name == job_name:
            return job.job_id
    raise ValueError(f"Job not found: {job_name}")

def get_all_clusters_and_warehouses(client: WorkspaceClient) -> tuple[list, list]:
    """Cache all available clusters and warehouses"""
    clusters_list = list(client.clusters.list())

    clusters_dict = {}
    for cluster in clusters_list:
        clusters_dict[cluster.cluster_name] = cluster.cluster_id

    warehouses_list = list(client.warehouses.list())

    warehouses_dict = {}
    for warehouse in warehouses_list:
        warehouses_dict[warehouse.name] = warehouse.id

    return clusters_dict, warehouses_dict


