# Databricks Workflow Jobs Synchronizer App

## Overview

This Databricks app (https://www.databricks.com/blog/introducing-databricks-apps) is used to synchronize workflow job definitions between a Databricks Workspace and a Git repository, implementing the "Jobs-as-Code" paradigm.

This is a simplified visual UI solution allowing to quickly synchronize all of the Job Definitions between workspace via JSON files in a Git Folder. It is a simplified alternative to using more targeted, flexibly configurable, but more technically complex and CI-CD oriented Databricks Asset Bundles (https://docs.databricks.com/en/dev-tools/bundles/index.html)

The indended audience of this app is unsophisticated organizations using Databricks, that are sufficiently mature to need 2-3 environments (workspaces) like DEV (UAT) and PROD and are using Workflow Jobs for scheduling, but are not technically mature enough to fully adopt Databricks Asset Bundles (https://docs.databricks.com/en/dev-tools/bundles/index.html)

## Features

- Export workflow job definitions from Databricks Workspace Workflows to a Git-enabled folder as JSON files

- Import workflow job definitions from a Git-enabled folder in Databricks Workspace Workflows

- Seamless resolution of job-to-job dependencies ("Run Job" task) by name

- Locally configurable mapping of Compute Resources (Interactive Clusters, SQL Warehouses) that can differ between environments

- Locally configurable mapping of User Names (Run As) that can differ between environments


## Deployment as a Databricks App

**If you are planning to use this capability to promote workflow definitions between environments, you need to deploy a copy of this app in each environment  both where you will be promoting the workflow definitions "from", e.g. DEV and "to" e.g. PROD workspaces**

Details on Databricks Apps: https://www.databricks.com/blog/introducing-databricks-apps

1. **Git Folder for version controlled job definitions**

    Create a Workspace Git Folder where workflow job definitions (JSON files) will be stored to, e.g. /Workspace/workflow-jobs-definitions, cloned from your own Git repository where you want to have the version controlled workflow job definitions. Typically it would be a single git repository used across multiple workspaces for different environments (DEV, TEST/QA, PROD), so you could do promotions.

    Note: if Databricks UI is not letting you create a Git Folder directly under /Workspace, you can create it under persomal Home folder, e.g. /Home/workflow-jobs-definitions and then move it to the shared location /Workspace/workflow-jobs-definitions

    Note: while you can use Git Folders located under personal Home folder, for this application it makes more sense to move them to a shared location, to simplify collaboration with other engineers and admins

2. **Git Folder with the app source code (clone from this github)**

    Create another Workspace Git Folder e.g. /Workspace/dbr-workflow-jobs-sync-app cloned from this repository (https://github.com/DmitriyAlergant-T1A/dbr-workflow-jobs-sync-app/). This is the app source code for deployment.

3. **Configure Environment Variables in app.yaml file**

    In the app.yaml file, configure the following environment variables to match your environment:
    
    **APP_MODE** variable controls the available synchronization modes, to avoid user mistakes and confusion between environments:
    - `Export` or `export`: Only allow exporting workflow jobs to Git
    - `Import` or `import`: Only allow importing workflow jobs from Git
    - `Both` or `both`: Allow both export and import modes (default)

    **NUM_THREADS** variable controls API requests concurrency when downloading and modifying jobs. For a larger environment (hundreds of jobs to validate and promote), use 4-5 threads. 
    However, newer and smaller Databricks workspaces have tighter API rate limits and you may experience deadlock-like freezes eventually ending up in timeouts. For a brand-new Databroicks Workspace, consider setting NUM_THREADS to 2 or even 1 to avoid these freezes.  

    **WORKSPACE_GIT_FOLDER_PATH** variable is a path to Git Folder for Job Definition JSON files that you created on Step 1. Note, you may point this variable to the full repository (Git Folder) root, but you can also point it to a subfolder inside of the Git Folder (ex: /jobs). It is relatively common to use a single Git repository hat combines both the Notebooks Source Code (/notebooks) and the Workflow Jobs Definitions (/jobs). You can configure the app accordingly, just make sure to be consistent across all environments.

    **RESOURCE_NAME_MAPPINGS_FILE_PATH** is a path to Resource Mapping file that you will create on Step 4 (below). You can use a regular workspace file (outside of Git Folder), or point it to a version-controlled file in a Git folder e.g. /Workspace/workflow-jobs-definitions/compute-name-mappings-prod.json 

    Example app.yaml env section


    ```yaml
    env:

    - name: "WORKSPACE_GIT_FOLDER_PATH"
        value: "/Workspace/Workflow Jobs GitHub Sync/test-dbr-jobs-github/jobs"                       
            # Adjust this path locally and point to a Git Folder with Job Definition files

    - name: "RESOURCE_NAME_MAPPINGS_FILE_PATH"
        value: "/Workspace/Workflow Jobs GitHub Sync/dbr-workflow-jobs-sync-app.config.json"     
            # Adjust this path locally and point to a file where you will configure resource mappings for Jobs Imports

    - name: "NUM_THREADS"
        value: "1"                                                     
            # Adjust to 4-6 to accelerate processing of large number of jobs if API Rate Limits allow. 
            # Reduce if you experience freezes and timeouts.

    - name: "APP_MODE"
        value: "Both"                                                  
            # Possible values: Export, Import, Both. Use this to safeguard environments and prevent mistakes.

4.  **Create and configure Resource Mappings file (only for Import environments - like Prod)**

    This step is only needed for environments where you will be Importing jobs "to" (ex: UAT, Production). This file is not needed for environments where you will be only Exporting jobs "from" (ex: DEV)

    Create and populate this file (at a location configured earlier in app.yaml file) with the environment-specific resource name mappings using the following example, e.g.
    ```
    {
        "compute_name_mappings": {
            "cluster_name_mappings": {
                "bi-users-dev-cluster": "bi-users-prod",
                "rajesh-dev": "etl-prod",
                "unknown": "etl-prod"
            }
            "warehouse_name_mappings": {
                "starter-warehouse": "etl-prod-warehouse-small",
                "unknown": "etl-prod-warehouse-small"
            }
        },
        "run_as_mappings": {
            "developer.lastname@company.com":       {"user_name":"super.admin@company.com"},
            "1234d931-d019-48a3-b606-431cc316ecdd": {"user_name":"super.admin@company.com"},
            "another.developer@company.com":        {"service_principal_name":"692bc6d0-ffa3-11ed-be56-0242ac120002"},
            "default":                              {"service_principal_name":"692bc6d0-ffa3-11ed-be56-0242ac120002"}
        }
    }
    ```

    *Note: it is recommended to always map the "unknown" compute cluster and warehouse names to some default cluster and warehouse that exists in the target environment. It often happens that an earlier created Workflow Job still exists in a Dev environment but the Cluster or SQL Warehouse is already deleted. Obviously such a job won't be functional in the Dev environment until repointed to valid compute resources, but no one notices. You may not want to see the validation errors for such jobs. The "unknown" name mapping is used in this situation.*

    *Note: for Run As attribute, you can mape user names and service principal IDs from the original environment to desired names in the current environment. You can also provide "default" mappings. If no mapping is found, the import process tries to keep the original Run As name - if it exists in the current environment. If it does not exist, the import process will fail for the affected job.*

5. **Create the App**

    In Compute > Apps, create a new App and give it a name, e.g. "**Workflow Jobs Synch App**". Wait a few seconds. 
    
    Review permissions on the app, by default it would only be granted to the Admins group - which is probably how you want to keep it.

6. **Deploy the App**

    Press the "**Deploy**" button and in the popup window choose the previously created Git Folder path with the cloned app source code (e.g. /Workspace/dbr-workflow-jobs-sync-app). 
    
    You can ignore the deployment instructions suggesting to use CLI - it is not neccessarily. Initial app deployment can be done from the Workspace UI without using the CLI.
    
    Once deployed, the app should be showing "🟢 Running" status, and a URL to access the UI

7. **Add App's Service Principal to Workspace Admins group**

    Go to Workspace Settings -> Identity and Access -> "admins" group and add this app's service principal as a member. You can find it by typing the app name that you used in Step 5, ex "workflow-jobs-synchronizer". 

    This is needed so that the app was able to access and modify all Workflow Jobs, and also so it coul set correct "Run As" user identities for imported jobs. Only admins are allowed to set "Run As" attribute to users other then themselves.

8. **Validate the deployment**

    Navigate to the App UI and review the "Workspace Information" drop-down section at the bottom, it should show valid values. 
    Click on the Resource Mappings "Show" dropdown and make sure it is showing the contents of the Resource Mappings file (from Step 4).

    *Note: If any Job Definition JSON files are already available in the Git Folder, it should show their count and last modified date*


## Additional Deployment Options

Besides deploying as a Databricks App, you can run this application as a container using the pre-built image from GitHub Container Registry.

### Using Docker Container

1. **Pull and run the container**

   ```bash
   docker run -p 8000:8000 \
     -e DATABRICKS_HOST="https://adb-....azuredatabricks.net/" \
     -e DATABRICKS_TOKEN="dapi..." \
     -e WORKSPACE_GIT_FOLDER_PATH="/Workspace/your-git-folder-path" \
     -e RESOURCE_NAME_MAPPINGS_FILE_PATH="/Workspace/dbr-workflow-jobs-sync-app.config.json" \
     -e APP_MODE="Both"
     ghcr.io/dmitriyalergant-t1a/dbr-workflow-jobs-sync-app:latest
   ```

   Access the application at http://localhost:8000

### Azure Container Apps Deployment

You can use the same docker image (see aboe) to deploy the application to Azure Container Apps using Azure CLI. Make sure to provide the required Environment Variables/Secrets, configure ingress port (8000), and enable one of the secure authentication options provided by Azure. 

NOTE, the app was originally designed for deployment as a Databricks App.  Even though you can deploy it in Azure Container Apps or any other standalone containerized web app hosting platform (assuming it provides some kind of external user authentication mechanism), the app will still rely on Databricks Workspace for persisting JSON files in Git Folers, Git Integration, Resource Mapping file, etc. You would need at least two separate deployments of this app (ex: DEV, PROD) pointing to their respective Databricks Workspaces to practically achieve the needs of promoting Workflow Jobs via Git Repository. 

## Usage

### Export Mode (Workflow Jobs to Git Repo), for DEV environment

1. Navigate to the app UI and make sure "Export Mode" toggle is selected. It should remember the mode choice for the next time you access the app in the same workspace.

2. Press "Export Workflow Jobs to JSON Files" button and wait for the process to complete

3. Review job-level results, any errors, and detailed log if neccessarily

4. Commit changes to Git. The "Push to Git Repo" button will navigate you directly to the Git Folder where the workflow job definitions were exported. Use built-in Databricks UI to enter Git mode, review the changes and to Commit & Push to Git. 

### Import Mode (Git Repo to Workflow Jobs), for PROD environment

1. Navigate to the App UI and make sure "Import Mode" toggle is selected. It should remember the mode choice for the next time you access the app in the same workspace.

2. Make sure your Git Folder with the workflow job definitions is up to date with the latest changes from the remote repository. The "Pull from Git Repo" button will navigate you directly to the configured Git Folder. Use built-in Databricks UI to enter Git mode and Pull recent changes.

3. Press "Validate Job Definition JSON Files" button to allow the app to validate and identify changes that will be applied during the import. Review the list of jobs and any errors that are reported. The jobs with validation error will be skipped and not be imported.

4. Press "Import New and Changed Jobs" button and wait for the process to complete.  Review job-level import results, any errors, and detailed log if neccessarily.

5. Optionally: press the "Remove Deleted Jobs" button to remove workflow jobs  whose JSON files were already deleted from the Git Repo.

### Troubleshooting

- **Error "Cluster ... does not exist in this workspace" or "Warehouse ... does not exist in this workspace"** during Import Validation: 
    - Go back to the Compute Mappings file (see Deployment step 4) and update the mappings, indicate what cluster or warehouse to use in this environment.  Make sure of the following:
    - Make sure that all cluster or warehouse names from the source environments are mentioned in the mappings file and mapped to the equivalent resources that exist in this environment
    - Make sure that the app Service Principal has access to all mapped cluster or warehouses - normally it should be added to 'admins' group anyway during deployment so it should not be an issue
    - The app correctly sees the Compute Resource name mappings file. Check the "Workspace Information" drop-down section at the bottom of the app UI, you should be able to see the contents of the mappings file.

- **Error "Referenced job ... not found in this workspace"** during Import Validation:
    -   Typically you can ingnore it first time. Import the other jobs (which import the referenced jobs), and then you can repeat the Validation and Import steps to make sure all jobs were imported successfully.
    -   In a very niche case of a circular dependency (jobs A and B reference each other, so neither of the jobs passes validation), you may need to one-time manually create a dummy job (A and/or B, or both) in this workspace to allow import to proceed. Dummy jobs can be extremely simple. Their contents will be replaced with correct details from Git Repo during the import.

- **Error "Failed to import job Batch-Job: 'name.lastname@company.com' cannot be set as run_as, either because the user does not exist or it is not active"** during Importing New and Changed Jobs
    - This means that the users or service principals used for "Run As" in the original environment were not found in this workspace.
    - Adjust the "Run As" mappings in the Resource Mappings file (see Deployment step 4), or make sure the original Run As user or service principal exists in this workspace.

## Development

### Versioning and Releases

This project follows [Semantic Versioning](https://semver.org/). Version numbers follow the pattern: MAJOR.MINOR.PATCH.

To create a new release:

1. Update CHANGELOG.md with your changes under a new version number
2. Commit your changes
3. Create and push a new tag:
   ```bash
   git tag v0.1.0  # Replace with your version
   git push origin main --tags
   ```

This will automatically trigger the GitHub Actions workflow to:
- Build the Docker image
- Tag it with the version number
- Push it to GitHub Container Registry (ghcr.io)

The Docker image will be available at: `ghcr.io/USERNAME/REPO:v0.1.0`

### Local Development Setup

See [Additional Deployment Options](#additional-deployment-options) section for local development instructions.
