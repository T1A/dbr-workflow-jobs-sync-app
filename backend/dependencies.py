import os
import logging
from fastapi import HTTPException
from databricks.sdk import WorkspaceClient
from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def create_workspace_client():
    logger.info("Creating new WorkspaceClient instance")
    return WorkspaceClient()

def get_workspace_client():
    client = create_workspace_client()
    logger.debug("Reusing existing WorkspaceClient instance")
    return client

def get_workspace_client_with_env_vars():
    """
    Get a Databricks workspace client with proper error handling and logging.
    Returns a WorkspaceClient instance or raises an HTTPException.
    """
    try:
        client = WorkspaceClient()
        logger.info("Successfully created WorkspaceClient with default credentials")
        return client
    except Exception as e:
        logger.warning(f"Failed to create WorkspaceClient with default credentials: {str(e)}")
        host = os.getenv("DATABRICKS_HOST")
        token = os.getenv("DATABRICKS_TOKEN")
        if not host or not token:
            logger.error("Missing required environment variables: DATABRICKS_HOST or DATABRICKS_TOKEN")
            raise HTTPException(
                status_code=500,
                detail="Missing required Databricks credentials. Please check environment variables."
            )
        try:
            client = WorkspaceClient(host=host, token=token)
            logger.info("Successfully created WorkspaceClient with environment variables")
            return client
        except Exception as e:
            logger.error(f"Failed to create WorkspaceClient with environment variables: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize Databricks client: {str(e)}"
            ) 