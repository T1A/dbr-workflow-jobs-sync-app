window.exportTask = function() {
    return {
        template: null,
        exportTaskId: null,
        exportStatus: 'idle',
        exportOutput: '',
        showLog: false,
        pollingInterval: null,
        progressStats: {
            total: 0,
            processed: 0,
            exported_modified: 0,
            exported_unchanged: 0,
            failed: 0,
            deleted: 0,
            percentComplete: 0
        },

        async init() {

            if (this.template) {
                return; // alerady initialized
            }

            console.log('export-task.js init called');
            
            try {
                // Load template
                const response = await fetch('/static/templates/export-task.html');
                if (!response.ok) {
                    throw new Error(`Failed to load template: ${response.statusText}`);
                }
                const templateText = await response.text();
                this.template = templateText;

                // Listen for the start-export event
                window.addEventListener('start-export', () => {
                    this.resetExport();
                    this.startExport();
                });

            } catch (err) {
                console.error('Error initializing export task:', err);
                this.exportStatus = 'failed';
                this.exportOutput = `Error: ${err.message}`;
            }
        },

        resetExport() {
            this.stopPolling();
            this.exportTaskId = null;
            this.exportStatus = 'idle';
            this.exportOutput = '';
            this.showLog = false;
            this.progressStats = {
                total: 0,
                processed: 0,
                exported_modified: 0,
                exported_unchanged: 0,
                failed: 0,
                deleted: 0,
                percentComplete: 0
            };
        },

        stopPolling() {
            console.log('Stopping export polling interval');
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
            }
        },

        async startExport() {
            try {
                this.stopPolling();
                this.exportStatus = 'Starting';
                this.exportOutput = '';
                
                console.log('Starting export...');
                const response = await fetch('/api/export/start', {
                    method: 'POST'
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(`${errorData.detail || response.statusText}`);
                }
                
                const data = await response.json();
                console.log('Export started with task ID:', data.exportTaskId);
                
                this.exportTaskId = data.exportTaskId;
                this.exportStatus = 'running';
                
                await this.pollExportStatus();
            } catch (err) {
                console.error('Error starting export:', err);
                this.exportStatus = 'failed';
                this.exportOutput += err.message;

                console.log('export-task.js this.exportOutput=', this.exportOutput);
                this.stopPolling();
            }
        },

        async pollExportStatus() {
            this.stopPolling(); // Clear any existing polling

            const poll = async () => {
                if (!this.exportTaskId) {
                    console.log('No export job ID, stopping polling');
                    this.stopPolling();
                    return;
                }
                
                try {
                    console.log('Polling status for task:', this.exportTaskId);
                    const response = await fetch(`/api/export/${this.exportTaskId}/status`);
                    
                    if (!response.ok) {
                        throw new Error(`Failed to fetch export status: ${response.statusText}`);
                    }
                    
                    const data = await response.json();
                    console.log('Export status update:', data);
                    
                    // Update status FIRST before other properties
                    this.exportStatus = data.status;
                    
                    // Then update other properties
                    this.exportOutput = data.output || this.exportOutput;
                    if (data.progress) {
                        const processedJobs = (data.progress.exported_modified || 0) + 
                                           (data.progress.exported_unchanged || 0) + 
                                           (data.progress.failed_jobs || 0);
                        
                        this.progressStats = {
                            total: data.progress.total_jobs || 0,
                            processed: processedJobs,
                            exported_modified: data.progress.exported_modified || 0,
                            exported_unchanged: data.progress.exported_unchanged || 0,
                            failed: data.progress.failed_jobs || 0,
                            deleted: data.progress.deleted_files || 0,
                            percentComplete: data.progress.total_jobs ? 
                                Math.round((processedJobs / data.progress.total_jobs) * 100) : 0
                        };
                    }

                    // If completed, ensure progress shows 100%
                    if (data.status === 'completed') {
                        this.progressStats.processed = this.progressStats.total;
                        this.progressStats.percentComplete = 100;
                    }

                    if (['completed', 'failed'].includes(data.status)) {
                        console.log('Export finished with status:', data.status);
                        
                        if (data.status === 'completed' && data.progress?.failed_jobs > 0) {
                            this.exportStatus = 'completed_with_errors';
                        }
                        
                        // Dispatch completion event
                        window.dispatchEvent(new CustomEvent('export-completed', {
                            detail: {
                                status: this.exportStatus,
                                progress: this.progressStats
                            }
                        }));
                        
                        this.stopPolling();
                        return;
                    }
                } catch (err) {
                    console.error('Error polling export status:', err);
                    this.exportStatus = 'failed';
                    this.exportOutput += `\nError: ${err.message}`;
                    this.stopPolling();
                    return;
                }
            };

            // Initial poll
            await poll();
            
            // Only set up polling interval if not already in a final state
            if (!['completed', 'failed', 'completed_with_errors'].includes(this.exportStatus)) {
                console.log('Setting up export polling interval');
                this.pollingInterval = setInterval(poll, 1000);
            } else {
                console.log('Not setting up polling - already in final state:', this.exportStatus);
            }
        }
    }
} 