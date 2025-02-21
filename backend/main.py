# backend/main.py
import logging
import sys
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
import os
from pathlib import Path

import dotenv
from backend.routers import api 

dotenv.load_dotenv()

# Custom StaticFiles class with cache control
class CustomStaticFiles(StaticFiles):
    def is_not_modified(self, response_headers, request_headers) -> bool:
        # Always return False to force revalidation
        return False

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if path.endswith(('.js', '.html')):  # Add cache control for both JS and HTML
            # Remove ETag if present
            if 'ETag' in response.headers:
                del response.headers['ETag']
            
            response.headers.update({
                'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Surrogate-Control': 'no-store'
            })
        return response

# Configure more detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Environment variable check function
def check_environment_variables():
    required_vars = [
        # "DATABRICKS_HOST",
        # "DATABRICKS_TOKEN",
        "WORKSPACE_GIT_FOLDER_PATH",
        "NUM_THREADS"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Check environment variables before creating the app
check_environment_variables()

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Add error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("An error occurred:")  # This will log the full traceback
    error_details = {
        "detail": str(exc),
        "type": str(type(exc).__name__)
    }
    logger.error(f"Error details: {error_details}")  # Log the error details
    return JSONResponse(
        status_code=500,
        content=error_details
    )

# Startup event handler
@app.on_event("startup")
async def startup_event():
    logger.info("Starting up FastAPI application")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Python path: {sys.path}")
    # Log environment variables (excluding sensitive data)
    logger.info(f"DATABRICKS_HOST is {'set' if os.getenv('DATABRICKS_HOST') else 'not set'}")
    logger.info(f"DATABRICKS_TOKEN is {'set' if os.getenv('DATABRICKS_TOKEN') else 'not set'}")
    logger.info(f"WORKSPACE_GIT_FOLDER_PATH: {os.getenv('WORKSPACE_GIT_FOLDER_PATH')}")

# Include the API router
app.include_router(api.router)

# Define frontend paths
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"

# Ensure the static directory exists
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files directory with custom handler
app.mount("/static", CustomStaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve index.html for the root path
@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

# Modify the catch-all route to include cache control for JS files
@app.get("/{file_path:path}")
async def serve_static_files(file_path: str):
    # First check if the file exists in the frontend directory
    full_path = FRONTEND_DIR / file_path
    
    if full_path.is_file():
        response = FileResponse(str(full_path))
        if file_path.endswith(('.js', '.html')):  # Add cache control for both JS and HTML
            # Remove ETag if present
            if 'ETag' in response.headers:
                del response.headers['ETag']
                
            response.headers.update({
                'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Surrogate-Control': 'no-store'
            })
        return response
    
    # If file not found, return index.html for client-side routing
    return FileResponse(str(FRONTEND_DIR / "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)