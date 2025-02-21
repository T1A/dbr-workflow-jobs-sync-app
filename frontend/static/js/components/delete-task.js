window.deleteTask = function() {
    return {
        template: null,
        deleteTaskId: null,
        deleteStatus: 'idle',
        deleteOutput: '',
        showLog: false,
        showJobStatuses: true,
        jobDeleteStatuses: [],
        pollingInterval: null,
        logRecords: [],
        progressStats: {
            total: 0,
            jobsToDelete: 0,
            deleted: 0,
            failed: 0,
            percentComplete: 0
        },
        tempDir: null,
        jobStatuses: null,

        get isInProgress() {
            return this.deleteStatus === 'running' || 
                   this.deleteStatus === 'Starting' || 
                   this.pollingInterval !== null;
        },

        async init() {

            if (this.template) {
                return; // alerady initialized
            }

            console.log('delete-task.js init called');
            
            try {
                // Load template
                const response = await fetch('/static/templates/delete-task.html');
                if (!response.ok) {
                    throw new Error(`Failed to load template: ${response.statusText}`);
                }
                this.template = await response.text();

                // Listen for the start-delete event
                window.addEventListener('start-delete', (event) => {
                    console.log('start-delete event received, event:', event);

                    if (event.detail && event.detail.jobStatuses) {
                        this.tempDir = event.detail.tempDir;
                        this.jobStatuses = event.detail.jobStatuses;
                        this.resetDelete();                        
                        this.startDeleteTask();
                    }
                    else {
                        this.resetDelete();
                        this.deleteStatus = 'Error: No jobs to delete';
                    }
                });

            } catch (err) {
                console.error('Error initializing delete task:', err);
                this.deleteStatus = 'failed';
                this.deleteOutput = `Error: ${err.message}`;
            }
        },

        resetDelete() {
            this.stopPolling();
            this.deleteTaskId = null;
            this.deleteStatus = 'idle';
            this.deleteOutput = '';
            this.showLog = false;
            
            const jobsToRemove = this.jobStatuses.filter(job => job.status === 'deleted').length;
            
            this.progressStats = {
                total: jobsToRemove,
                jobsToDelete: jobsToRemove,
                deleted: 0,
                failed: 0,
                percentComplete: 0
            };

            console.log('Delete task stats reset, jobs to remove:', jobsToRemove);
        },

        stopPolling() {
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
            }
        },

        async startDeleteTask() {
            // Prevent starting if already in progress
            if (this.isInProgress) {
                console.log('Delete task already in progress, ignoring start request');
                return;
            }

            try {
                if (!this.jobStatuses || !this.jobStatuses.length) {
                    throw new Error('No jobs specified for deletion');
                }

                this.stopPolling();
                this.deleteStatus = 'Starting';
                this.deleteOutput = '';
                
                const requestBody = { 
                    jobStatuses: this.jobStatuses,
                    tempDir: this.tempDir
                };
                
                console.log('Sending delete request with data:', requestBody);
                
                const response = await fetch('/api/delete/start', {
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
                if (!data.deleteTaskId) {
                    throw new Error('Invalid response: missing delete task ID');
                }
                this.deleteTaskId = data.deleteTaskId;
                this.deleteStatus = 'running';
                
                await this.pollDeleteStatus();
            } catch (err) {
                console.error('Error starting delete task:', err);
                this.deleteStatus = 'failed';
                this.deleteOutput = `Error: ${err.message}`;
                this.stopPolling();
            }
        },

        async pollDeleteStatus() {
            this.stopPolling();

            const poll = async () => {
                if (!this.deleteTaskId) {
                    console.log('No delete task ID, stopping polling');
                    this.stopPolling();
                    return;
                }
                
                try {
                    console.log('Polling delete status for task:', this.deleteTaskId);
                    const response = await fetch(`/api/delete/${this.deleteTaskId}/status`);
                    
                    if (!response.ok) {
                        throw new Error(`Failed to fetch delete status: ${response.statusText}`);
                    }
                    
                    const data = await response.json();
                    console.log('Delete status update:', data);
                    
                    if (!data.status) {
                        throw new Error('Invalid status response: missing status field');
                    }
                    
                    this.deleteStatus = data.status;
                    this.deleteOutput = data.output || this.deleteOutput;
                    this.logRecords = data.logRecords || [];
                    this.jobDeleteStatuses = data.jobDeleteStatuses || [];
                    
                    if (data.progress) {
                        this.progressStats = {
                            total: this.progressStats.total,
                            jobsToDelete: this.progressStats.jobsToDelete,
                            deleted: data.progress.deleted || 0,
                            failed: data.progress.failed_jobs || 0,
                        };
                        
                        const processedJobs = this.progressStats.deleted + this.progressStats.failed;
                        const totalJobsToProcess = this.progressStats.jobsToDelete;
                        
                        this.progressStats.percentComplete = totalJobsToProcess > 0 ? 
                            Math.round((processedJobs / totalJobsToProcess) * 100) : 0;
                    }

                    if (['completed', 'failed', 'completed_with_errors'].includes(data.status)) {
                        if (data.status === 'completed' && data.progress?.failed_jobs > 0) {
                            this.deleteStatus = 'completed_with_errors';
                        }
                        
                        console.log('Delete task finished with status:', data.status);
                        this.stopPolling();
                        // Dispatch event when delete is complete
                        console.log('Dispatching delete-completed event');
                        window.dispatchEvent(new CustomEvent('delete-completed', {
                            detail: {
                                status: data.status,
                                output: data.output,
                                jobDeleteStatuses: data.jobDeleteStatuses,
                                progress: data.progress
                            }
                        }));
                        // Dispatch event to refresh workspace info
                        console.log('Dispatching refresh-workspace-info event');
                        window.dispatchEvent(new CustomEvent('refresh-workspace-info'));
                        return;
                    }
                } catch (err) {
                    console.error('Error polling delete status:', err);
                    this.deleteStatus = 'failed';
                    this.deleteOutput = `Error: ${err.message}`;
                    this.stopPolling();
                    return;
                }
            };

            // Initial poll
            await poll();
            
            // Set up polling interval if not in final state
            if (!['completed', 'failed', 'completed_with_errors'].includes(this.deleteStatus)) {
                console.log('Setting up polling interval');
                this.pollingInterval = setInterval(poll, 1000);
            } else {
                console.log('Not setting up polling - already in final state:', this.deleteStatus);
            }
        }
    }
} 