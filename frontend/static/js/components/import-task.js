window.importTask = function() {
    return {
        template: null,
        importTaskId: null,
        importStatus: 'idle',
        importOutput: '',
        showLog: false,
        showJobStatuses: true,
        jobImportStatuses: [],
        pollingInterval: null,
        logRecords: [],
        progressStats: {
            total: 0,
            jobsToImport: 0,
            imported: 0,
            skipped_unchanged: 0,
            failed: 0,
            percentComplete: 0
        },
        tempDir: null,
        jobStatuses: null,

        get isInProgress() {
            return this.importStatus === 'running' || 
                   this.importStatus === 'Starting' || 
                   this.pollingInterval !== null;
        },

        async init() {

            if (this.template) {
                return; // alerady initialized
            }


            console.log('import-task.js init called');
            
            try {
                // Load template
                const response = await fetch('/static/templates/import-task.html');
                if (!response.ok) {
                    throw new Error(`Failed to load template: ${response.statusText}`);
                }
                this.template = await response.text();

                // Listen for the start-import event
                window.addEventListener('start-import', (event) => {
                    console.log('start-import event received, event:', event);

                    if (event.detail && event.detail.jobStatuses) {
                        const numJobs = event.detail.jobStatuses.length;
                        this.setTaskInfo(event.detail.tempDir, event.detail.jobStatuses);
                        this.resetImport(numJobs);
                        this.startImportTask();
                    }
                    else {
                        this.resetImport(0);
                        this.importStatus = 'Error: No jobs to import';
                    }
                });

            } catch (err) {
                console.error('Error initializing import task:', err);
                this.importStatus = 'failed';
                this.importOutput = `Error: ${err.message}`;
            }
        },

        resetImport(totalJobs = 0) {
            this.stopPolling();
            this.importTaskId = null;
            this.importStatus = 'idle';
            this.importOutput = '';
            this.showLog = false;
            this.jobImportStatuses = [];
            this.logRecords = [];
            
            // Reset only progress stats, preserve task information (tempDir and jobStatuses)
            this.progressStats = {
                total: totalJobs,
                jobsToImport: totalJobs,
                imported: 0,
                skipped_unchanged: 0,
                failed: 0,
                percentComplete: 0
            };

            console.log('Import task stats reset, totalJobs:', totalJobs);
        },

        setTaskInfo(tempDir, jobStatuses) {
            this.tempDir = tempDir;
            this.jobStatuses = jobStatuses;
            console.log('Import task info set:', { tempDir, jobCount: jobStatuses.length });
        },

        stopPolling() {
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
            }
        },

        async startImportTask() {
            // Prevent starting if already in progress
            if (this.isInProgress) {
                console.log('Import task already in progress, ignoring start request');
                return;
            }

            try {
                if (!this.tempDir) {
                    throw new Error('No temporary directory specified for import');
                }
                if (!this.jobStatuses || !this.jobStatuses.length) {
                    throw new Error('No jobs specified for import');
                }

                // Only count jobs that need to be imported
                this.progressStats.total = this.jobStatuses.filter(
                    job => job.status === 'new' || job.status === 'changed'
                ).length;
                this.progressStats.jobsToImport = this.progressStats.total;

                this.stopPolling();
                this.importStatus = 'Starting';
                this.importOutput = '';
                
                const requestBody = { 
                    jobStatuses: this.jobStatuses,
                    tempDir: this.tempDir
                };
                
                console.log('Sending import request with data:', requestBody);
                
                const response = await fetch('/api/import/start', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(requestBody)
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    const errorMessage = errorData.detail 
                        ? (Array.isArray(errorData.detail) 
                            ? errorData.detail.map(err => `${err.loc.join('.')}: ${err.msg}`).join('; ')
                            : errorData.detail)
                        : 'Unknown error occurred';
                    throw new Error(errorMessage);
                }
                
                const data = await response.json();
                if (!data.importTaskId) {
                    throw new Error('Invalid response: missing import task ID');
                }
                this.importTaskId = data.importTaskId;
                this.importStatus = 'running';
                
                await this.pollImportStatus();
            } catch (err) {
                console.error('Error starting import:', err);
                this.importStatus = 'failed';
                this.importOutput = `Error: ${err.message}`;
                this.stopPolling();
            }
        },

        async pollImportStatus() {
            this.stopPolling();

            const poll = async () => {
                if (!this.importTaskId) {
                    console.log('No import job ID, stopping polling');
                    this.stopPolling();
                    return;
                }
                
                try {
                    console.log('Polling import status for task:', this.importTaskId);
                    const response = await fetch(`/api/import/${this.importTaskId}/status`);
                    
                    if (!response.ok) {
                        throw new Error(`Failed to fetch import status: ${response.statusText}`);
                    }
                    
                    const data = await response.json();
                    console.log('Import status update:', data);
                    
                    if (!data.status) {
                        throw new Error('Invalid status response: missing status field');
                    }
                    
                    this.importStatus = data.status;
                    this.importOutput = data.output || this.importOutput;
                    this.logRecords = data.logRecords || [];
                    this.jobImportStatuses = data.jobImportStatuses || [];
                    
                    if (data.progress) {
                        this.progressStats = {
                            total: this.progressStats.total,
                            jobsToImport: this.progressStats.jobsToImport,
                            imported: data.progress.imported || 0,
                            skipped_unchanged: 0, // We no longer track skipped jobs
                            failed: data.progress.failed_jobs || 0,
                        };
                        
                        const processedJobs = this.progressStats.imported + 
                                            this.progressStats.failed;
                        
                        const totalJobsToProcess = this.progressStats.jobsToImport;
                        
                        this.progressStats.percentComplete = totalJobsToProcess > 0 ? 
                            Math.round((processedJobs / totalJobsToProcess) * 100) : 0;
                    }

                    if (['completed', 'failed', 'completed_with_errors'].includes(data.status)) {
                        if (data.status === 'completed' && data.progress?.failed_jobs > 0) {
                            this.importStatus = 'completed_with_errors';
                        }
                        
                        console.log('Import finished with status:', data.status);
                        this.stopPolling();
                        // Dispatch event when import is complete
                        console.log('Dispatching import-completed event');
                        window.dispatchEvent(new CustomEvent('import-completed', {"detail": data}));
                        // Dispatch event to refresh workspace info
                        console.log('Dispatching refresh-workspace-info event');
                        window.dispatchEvent(new CustomEvent('refresh-workspace-info'));
                        return;
                    }
                } catch (err) {
                    console.error('Error polling import status:', err);
                    this.importStatus = 'failed';
                    this.importOutput = `Error: ${err.message}`;
                    this.stopPolling();
                    return;
                }
            };

            // Initial poll
            await poll();
            
            // Set up polling interval if not in final state
            if (!['completed', 'failed', 'completed_with_errors'].includes(this.importStatus)) {
                console.log('Setting up polling interval');
                this.pollingInterval = setInterval(poll, 1000);
            } else {
                console.log('Not setting up polling - already in final state:', this.importStatus);
            }
        }
    }
} 