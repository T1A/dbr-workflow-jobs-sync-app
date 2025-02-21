FROM python:3.12-slim

WORKDIR /app

# Define environment variables with defaults
ENV WORKSPACE_GIT_FOLDER_PATH=/Workspace/workflow-jobs-definitions/jobs \
    RESOURCE_NAME_MAPPINGS_FILE_PATH=/Workspace/mappings.json \
    DATABRICKS_HOST="" \
    DATABRICKS_TOKEN="" \
    NUM_THREADS=5 \
    APP_MODE=Both

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"] 