window.workspaceInfo = function() {
    return {
        template: null,
        workspaceInfo: {},
        error: null,
        loading: true,
        isExpanded: true,
        computeMappingsExpanded: false,

        async init() {

            if (this.template) {
                return; // alerady initialized
            }

            console.log('workspace-info.js init called');
            try {
                // Load template first
                const response = await fetch('/static/templates/workspace-info.html');
                this.template = await response.text();
                
                // Start fetching data in the background without awaiting
                this.fetchWorkspaceInfo();

                // Listen for task start events
                window.addEventListener('collapse-workspace-info', () => {
                    this.isExpanded = false;
                });

                // Listen for refresh events
                window.addEventListener('refresh-workspace-info', () => {
                    console.log('Refreshing workspace info after import completion');
                    this.fetchWorkspaceInfo();
                });
            } catch (err) {
                console.error('Error initializing workspace info:', err);
                this.error = err.message;
            }
        },

        async fetchWorkspaceInfo() {
            this.loading = true;
            this.error = null;
            
            // Start all fetches in parallel without blocking initialization
            Promise.all([
                this.fetchWorkspaceFolder(),
                this.fetchWorkspaceFilesInfo(),
                this.fetchWorkflowJobsCount(),
                this.fetchComputeMappings()
            ]).then(() => {
                this.loading = false;
            }).catch(err => {
                console.error('Error fetching workspace info:', err);
                this.error = err.message;
                this.loading = false;
            });
        },

        async fetchWorkspaceFolder() {
            try {
                const response = await fetch('/api/workspace-info/folder');
                if (!response.ok) throw new Error(`Failed to fetch workspace folder: ${response.statusText}`);
                const data = await response.json();
                this.workspaceInfo = { 
                    ...this.workspaceInfo, 
                    workspace_git_folder: data.workspace_git_folder,
                    databricks_host: data.databricks_host
                };
            } catch (err) {
                console.error('Error fetching workspace folder:', err);
                this.error = err.message;
            }
        },

        async fetchWorkspaceFilesInfo() {
            try {
                const response = await fetch('/api/workspace-info/files');
                if (!response.ok) throw new Error(`Failed to fetch workspace files info: ${response.statusText}`);
                const data = await response.json();
                this.workspaceInfo = { 
                    ...this.workspaceInfo, 
                    workspace_last_modified: data.workspace_last_modified,
                    json_files_count: data.json_files_count 
                };
            } catch (err) {
                console.error('Error fetching workspace files info:', err);
                this.error = err.message;
            }
        },

        async fetchWorkflowJobsCount() {
            try {
                const response = await fetch('/api/workspace-info/jobs-count');
                if (!response.ok) throw new Error(`Failed to fetch workflow jobs count: ${response.statusText}`);
                const data = await response.json();
                this.workspaceInfo = { ...this.workspaceInfo, workflow_jobs_count: data.workflow_jobs_count };
            } catch (err) {
                console.error('Error fetching workflow jobs count:', err);
                this.error = err.message;
            }
        },

        async fetchComputeMappings() {
            try {
                const response = await fetch('/api/workspace-info/compute-cluster-mappings');
                if (!response.ok) throw new Error(`Failed to fetch compute mappings: ${response.statusText}`);
                const data = await response.json();
                this.workspaceInfo = { 
                    ...this.workspaceInfo, 
                    compute_mappings: data.compute_cluster_mappings,
                    mappings_file_path: data.mappings_file_path
                };
            } catch (err) {
                console.error('Error fetching compute mappings:', err);
                this.error = err.message;
            }
        }
    };
} 