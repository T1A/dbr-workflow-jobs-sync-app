window.importValidationTaskComponent = function() {
    return {
        template: null,
        importStatus: 'idle',
        importTempDir: null,
        validationIssues: [],
        importTaskId: null,
        importOutput: '',
        showImportLog: false,
        taskIssues: [],
        jobStatuses: [],
        importMessage: '',
        pollingInterval: null,
        importSummary: {
            new: 0,
            changed: 0,
            unchanged: 0,
            deleted: 0,
            error: 0
        },
        showDifferences: false,
        activeFilters: {
            new: false,
            changed: false,
            unchanged: false,
            deleted: false,
            error: false
        },
        progressStats: {
            total_items: 0,
            processed_items: 0,
            files_to_transfer: 0,
            files_transferred: 0,
            jobs_to_validate: 0,
            jobs_validated: 0
        },
        get isInProgress() {
            return this.importStatus === 'in_progress' || 
                   this.importStatus === 'Starting' || 
                   this.pollingInterval !== null;
        },
        get filteredJobStatuses() {
            const hasActiveFilters = Object.values(this.activeFilters).some(filter => filter);
            if (!hasActiveFilters) {
                return this.jobStatuses;
            }
            return this.jobStatuses.filter(job => this.activeFilters[job.status]);
        },

        toggleFilter(filterType) {
            this.activeFilters[filterType] = !this.activeFilters[filterType];
        },

        async init() {

            if (this.template) {
                return; // alerady initialized
            }

            try {
                console.log('import-validation-task init called...');
                const response = await fetch('/static/templates/import-validation-task.html');
                if (!response.ok) {
                    throw new Error(`Failed to load template: ${response.statusText}`);
                }
                const templateText = await response.text();
                this.template = templateText;
                
                // Listen for the start-pre-import-validation event
                window.addEventListener('start-pre-import-validation', () => {
                    console.log('start-pre-import-validation event received');
                    this.startImportValidation();
                });
            } catch (err) {
                console.error('Error initializing import validation task:', err);
                this.importStatus = 'failed';
                this.importMessage = `Error: ${err.message}`;
            }
        },

        stopPolling() {
            console.log('Stopping polling interval');
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
            }
        },

        async startImportValidation() {
            // Prevent starting if already in progress
            if (this.isInProgress) {
                console.log('Import validation already in progress, ignoring start request');
                return;
            }

            try {
                this.stopPolling(); // Clear any existing polling
                this.importStatus = 'in_progress';
                this.importOutput = '';
                this.taskIssues = [];
                this.jobStatuses = [];
                this.importMessage = 'Starting import validation...';
                
                console.log('Starting import validation...');
                const response = await fetch('/api/pre-import-validation/start', {
                    method: 'POST'
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to start import validation: ${response.statusText}`);
                }
                
                const data = await response.json();
                console.log('Import validation started:', data);
                
                this.importTaskId = data.importTaskId;
                await this.pollImportStatus();
            } catch (err) {
                console.error('Error starting import validation:', err);
                this.importStatus = 'failed';
                this.importMessage = `Error: ${err.message}`;
                this.importOutput += `\nError: ${err.message}`;
            }
        },

        async pollImportStatus() {
            this.stopPolling(); // Clear any existing polling

            const poll = async () => {
                if (!this.importTaskId) {
                    console.log('No import job ID, stopping polling');
                    this.stopPolling();
                    return;
                }
                
                try {
                    console.log('Polling import status for task:', this.importTaskId);
                    const response = await fetch(`/api/pre-import-validation/${this.importTaskId}/status`);
                    
                    if (!response.ok) {
                        throw new Error(`Failed to fetch import status: ${response.statusText}`);
                    }
                    
                    const data = await response.json();
                    console.log('Import status update:', data);
                    
                    // Update status before other properties to ensure watcher triggers properly
                    this.importStatus = data.status;
                    
                    // Update other properties
                    this.importMessage = data.message || this.importMessage;
                    this.taskIssues = data.taskIssues || [];
                    this.jobStatuses = data.jobStatuses || [];
                    this.importOutput = data.logRecords?.join('') || '';

                    // Calculate summary counts
                    this.importSummary = {
                        new: this.jobStatuses.filter(job => job.status === 'new').length,
                        changed: this.jobStatuses.filter(job => job.status === 'changed').length,
                        unchanged: this.jobStatuses.filter(job => job.status === 'unchanged').length,
                        deleted: this.jobStatuses.filter(job => job.status === 'deleted').length,
                        error: this.jobStatuses.filter(job => job.status === 'error').length
                    };

                    // Update progress stats
                    if (data.progress) {
                        this.progressStats = data.progress;
                    }

                    // Stop polling if we're in a final state
                    if (['completed', 'completed_with_warnings', 'completed_with_errors', 'completed_no_changes'].includes(data.status)) {
                        console.log('Import validation finished with status:', data.status);
                        this.stopPolling();
                        console.log('Dispatching pre-import-validation-completed event with details');
                        window.dispatchEvent(new CustomEvent('pre-import-validation-completed', {
                            detail: {
                                status: data.status,
                                message: data.message,
                                taskIssues: data.taskIssues || [],
                                jobStatuses: data.jobStatuses || [],
                                summary: this.importSummary,
                                tempDir: data.tempDir
                            }
                        }));
                        return;
                    } else if (data.status === 'failed') {
                        console.log('Import validation failed');
                        this.stopPolling();
                        return;
                    }
                } catch (err) {
                    console.error('Error polling import status:', err);
                    this.importStatus = 'failed';
                    this.importMessage = `Error: ${err.message}`;
                    this.importOutput += `\nError: ${err.message}`;
                    this.stopPolling();
                    return; // Exit the polling function
                }
            };

            // Initial poll
            await poll();
            
            // Only set up polling interval if not already in a final state
            if (!['completed', 'failed', 'completed_with_warnings', 'completed_with_errors', 'completed_no_changes'].includes(this.importStatus)) {
                console.log('Setting up polling interval');
                this.pollingInterval = setInterval(poll, 1000);
            } else {
                console.log('Not setting up polling - already in final state:', this.importStatus);
            }
        }
    }
} 