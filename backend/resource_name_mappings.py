import json, json5
import logging
from fastapi import HTTPException
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat
import os


logger = logging.getLogger(__name__)


# 1. Compute Cluster Mappings Functions

RESOURCE_NAME_MAPPINGS_FILE_PATH = os.getenv(
    'RESOURCE_NAME_MAPPINGS_FILE_PATH',
    "/Workspace/dbr-workflow-jobs-sync-app.config.json"
)

def get_resource_name_mappings(client: WorkspaceClient):
    try:
        with client.workspace.download(RESOURCE_NAME_MAPPINGS_FILE_PATH) as file:
            config_content = file.read().decode('utf-8')
            config = json5.loads(config_content)
            mappings = {
                "compute_name_mappings": config.get("compute_name_mappings", {}),
                "run_as_mappings": config.get("run_as_mappings", {})
            }
            return mappings
    except Exception as e:
        logger.warning(f"Config file not found or error reading it: {str(e)}")
        # Create default empty config
        try:
            config = {
                "compute_name_mappings": {},
                "run_as_mappings": {}
            }
            config_content = json.dumps(config, indent=2)
            client.workspace.upload(
                path=RESOURCE_NAME_MAPPINGS_FILE_PATH,
                content=config_content.encode('utf-8'),
                overwrite=True,
                format=ImportFormat.RAW
            )
            logger.info("Created default empty config file")
        except Exception as create_error:
            logger.error(f"Failed to create default config: {str(create_error)}")
        return {}

def update_resource_name_mappings(client: WorkspaceClient, mappings: dict):
    client = WorkspaceClient()
    config = {"compute_name_mappings": mappings}
    try:
        config_content = json.dumps(config, indent=2)
        client.workspace.upload(
            path=RESOURCE_NAME_MAPPINGS_FILE_PATH,
            content=config_content.encode('utf-8'),
            overwrite=True,
            format=ImportFormat.RAW
        )
        logger.info("Compute cluster mappings updated successfully.")
    except Exception as e:
        logger.error(f"Error updating compute cluster mappings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update compute cluster mappings.")