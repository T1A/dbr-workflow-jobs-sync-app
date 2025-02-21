window.importWorkflow = function() {
    return {

        STAGES: {
            NONE: 'NONE',
            PRE_VALIDATION: 'PRE_VALIDATION',
            IMPORT: 'IMPORT',
            DELETE: 'DELETE'
        },

        currentStage: "NONE",

        stageResults: {
            PRE_VALIDATION: null,
            IMPORT: null,
            DELETE: null
        },
        
        template: '',
        validationTaskComponentInstance: null,
        importTaskComponentInstance: null,
        deleteTaskComponentInstance: null,
        componentsInitialized: false,

        async init() {

            if (this.template) {
                return; // alerady initialized
            }
            
            console.log('import-workflow init called');

            if (!this.componentsInitialized) {
                // Create shared instances
                this.validationTaskComponentInstance = window.importValidationTaskComponent();
                this.importTaskComponentInstance = window.importTask();
                this.deleteTaskComponentInstance = window.deleteTask();
                await this.validationTaskComponentInstance.init();
                await this.importTaskComponentInstance.init();
                await this.deleteTaskComponentInstance.init();
                this.componentsInitialized = true;
            }

           // Load template
           const response = await fetch('/static/templates/import-workflow.html');
           this.template = await response.text();

            // Listen for task completion events
            window.addEventListener('pre-import-validation-completed', (event) => {
                console.log('pre-import-validation-completed event received:', event.detail);
                this.stageResults.PRE_VALIDATION = event.detail;
                this.currentStage = this.STAGES.PRE_VALIDATION;
            });
            
            window.addEventListener('import-completed', (event) => {
                this.stageResults.IMPORT = event.detail;
                this.currentStage = this.STAGES.IMPORT;

                console.log("Received import-completed event. this.stageResults.IMPORT: ", this.stageResults.IMPORT);
            });
            
            window.addEventListener('delete-completed', (event) => {
                this.stageResults.DELETE = event.detail;
                this.currentStage = this.STAGES.DELETE;
            });
        },

        isStageCompleted(stage) {
            return this.stageResults[stage] !== null;
        },
        getImportButtonText() {
            const baseText = '3. Import New and Changed Jobs';
            if (!this.stageResults.PRE_VALIDATION?.jobStatuses) {
                return baseText;
            }
            const count = this.stageResults.PRE_VALIDATION.jobStatuses.filter(
                job => job.status === 'new' || job.status === 'changed'
            ).length;
            return count !== null ? `${baseText} (${count})` : baseText;
        },

        getDeleteButtonText() {
            const baseText = '4. Remove Deleted Jobs';
            if (!this.stageResults.PRE_VALIDATION?.jobStatuses) {
                return baseText;
            }
            const count = this.stageResults.PRE_VALIDATION.jobStatuses.filter(
                job => job.status === 'deleted'
            ).length;
            return count !== null ? `${baseText} (${count})` : baseText;
        },

        handlePull() {
            // Dispatch event to trigger the global pull handler
            window.dispatchEvent(new CustomEvent('workflow-pull-clicked'));
            console.log('workflow-pull-clicked event dispatched');
        },

        canStartStage(stage) {
            switch (stage) {
                case this.STAGES.PRE_VALIDATION:
                    
                    return true;

                case this.STAGES.IMPORT:

                    const hasJobsToImport = this.stageResults.PRE_VALIDATION?.jobStatuses.some(
                        job => job.status === 'new' || job.status === 'changed'
                    );

                    return this.isStageCompleted(this.STAGES.PRE_VALIDATION) && hasJobsToImport;

                case this.STAGES.DELETE:

                    const hasJobsToDelete = this.stageResults.PRE_VALIDATION?.jobStatuses.some(
                        job => job.status === 'deleted'
                    );

                    return this.isStageCompleted(this.STAGES.PRE_VALIDATION) && hasJobsToDelete;

                default:
                    
                    return false;
            }
        },

        getValidationTaskComponent() {
            return this.validationTaskComponentInstance;
        },

        getImportTaskComponent() {
            return this.importTaskComponentInstance;
        },

        getDeleteTaskComponent() {
            return this.deleteTaskComponentInstance;
        },

        transitionWorkflowStage(newStage) {
            if (!this.canStartStage(newStage)) return;
            
            switch (newStage) {
                case this.STAGES.PRE_VALIDATION:
                    // Check if validation is already in progress
                    if (this.validationTaskComponentInstance.isInProgress) {
                        console.log('Validation already in progress, ignoring transition request');
                        return;
                    }

                    // If we're starting from the beginning, or a button is clicked again while on the same stage, (re)start the actual task
                    if (this.currentStage == null || this.currentStage == this.STAGES.NONE || this.currentStage == this.STAGES.PRE_VALIDATION) {
                        this.stageResults = {
                            PRE_VALIDATION: null,
                            IMPORT: null,
                            DELETE: null
                        };

                        window.dispatchEvent(new CustomEvent('start-pre-import-validation', {
                            detail: { timestamp: Date.now() }
                        }));
                    }

                    // Show the pre-validation component
                    this.currentStage = this.STAGES.PRE_VALIDATION;
                    break;

                case this.STAGES.IMPORT:
                    // Check if import is already in progress
                    if (this.importTaskComponentInstance.isInProgress) {
                        console.log('Import already in progress, ignoring transition request');
                        return;
                    }

                    console.log("IMPORT stage transitioning... this.stageResults.IMPORT: ", this.stageResults.IMPORT);

                    // If we're starting from the beginning, or a button is clicked again while on the same stage, (re)start the actual task
                    if (this.stageResults.IMPORT == null || this.currentStage == this.STAGES.IMPORT) {
                        this.stageResults.IMPORT = null;

                        const validationResults = this.stageResults.PRE_VALIDATION;

                        if (!validationResults || !validationResults.jobStatuses) {
                            throw new Error('No validation results available. Please run pre-import validation first.');
                        }

                        // Filter out unchanged and error jobs before sending to backend
                        const jobsToImport = validationResults.jobStatuses.filter(
                            job => job.status === 'new' || job.status === 'changed'
                        );

                        window.dispatchEvent(new CustomEvent('start-import', {
                            detail: {
                                jobStatuses: jobsToImport,
                                tempDir: validationResults.tempDir
                            }
                        }));
                    }

                    // Show the Import component
                    this.currentStage = this.STAGES.IMPORT;
                    break;

                case this.STAGES.DELETE:
                    // Check if delete is already in progress
                    if (this.deleteTaskComponentInstance.isInProgress) {
                        console.log('Delete already in progress, ignoring transition request');
                        return;
                    }

                    // If we're starting from the beginning, or a button is clicked again while on the same stage, (re)start the actual task
                    if (this.stageResults.DELETE == null || this.currentStage == this.STAGES.DELETE) {
                        this.stageResults.DELETE = null;

                        const validationResults = this.stageResults.PRE_VALIDATION;

                        if (!validationResults || !validationResults.jobStatuses) {
                            throw new Error('No validation results available. Please run pre-import validation first.');
                        }
                        window.dispatchEvent(new CustomEvent('start-delete', {
                            detail: {
                                jobStatuses: validationResults.jobStatuses,
                                tempDir: validationResults.tempDir
                            }
                        }));
                    }

                    // Show the Delete component
                    this.currentStage = this.STAGES.DELETE;
                    break;
            }
        },

    };
} 