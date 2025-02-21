# Development Guide

This guide is for developers who want to build and run the application from source.

## Local Development Setup

1. **Using Local Python Environment**

   ```bash
   # Create and activate virtual environment
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt

   # Run the application
   uvicorn backend.main:app --reload --port 8000
   ```

2. **Using Docker**

   ```bash
   # Build the image
   docker build -t dbr-workflow-sync .

   # Run the container
   docker run -p 8000:8000 \
     -e DATABRICKS_HOST="https://your-workspace.cloud.databricks.com" \
     -e DATABRICKS_TOKEN="dapi..." \
     dbr-workflow-sync
   ```

## Environment Variables

The application uses the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| WORKSPACE_GIT_FOLDER_PATH | /Workspace/workflow-jobs-definitions/jobs | Path to Git folder in Databricks workspace |
| RESOURCE_NAME_MAPPINGS_FILE_PATH | /Workspace/mappings.json | Path to resource mappings file |
| DATABRICKS_HOST | "" | Databricks workspace URL |
| DATABRICKS_TOKEN | "" | Databricks Personal Access Token |
| NUM_THREADS | 5 | Number of threads for parallel processing |
| APP_MODE | Both | Application mode (Export/Import/Both) |

## Building and Publishing

1. **Building Docker Image Locally**
   ```bash
   docker build -t dbr-workflow-sync .
   ```

2. **Publishing to GitHub Container Registry**

   The GitHub Actions workflow (.github/workflows/docker-publish.yml) automatically builds and publishes the container when:
   - A new tag is pushed (v*.*.*)
   - Changes are pushed to main branch
   - Pull requests are created against main branch

   To manually trigger a release:
   ```bash
   # Update version in backend/version.py
   # Update CHANGELOG.md
   git add .
   git commit -m "Release vX.Y.Z"
   git tag vX.Y.Z
   git push origin main --tags
   ```

## VS Code Configuration

A launch configuration is provided in .vscode/launch.json for debugging:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: FastAPI",
            "type": "python",
            "request": "launch",
            "module": "uvicorn",
            "args": ["backend.main:app", "--reload", "--port", "8000"],
            "python": "${workspaceFolder}/.venv/bin/python",
            "jinja": true,
            "console": "integratedTerminal"
        }
    ]
}
``` 