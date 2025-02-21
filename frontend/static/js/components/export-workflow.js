window.exportWorkflow = function() {
    return {
        STAGES: {
            NONE: 'NONE',
            EXPORT: 'EXPORT',
            PUSH: 'PUSH'
        },

        currentStage: "NONE",
        stageResults: {
            EXPORT: null,
            PUSH: null
        },
        
        template: null,
        exportTaskComponentInstance: null,
        componentsInitialized: false,
        
        async init() {
            console.log('export-workflow init called');
            if (!this.componentsInitialized) {
                // Create shared instances
                this.exportTaskComponentInstance = window.exportTask();
                await this.exportTaskComponentInstance.init()
                this.componentsInitialized = true;
            }

            // Load template
            const response = await fetch('/static/templates/export-workflow.html');
            this.template = await response.text();

            // Listen for task completion events
            window.addEventListener('export-completed', (event) => {
                console.log('export-completed event received:', event.detail);
                this.stageResults.EXPORT = event.detail;
                this.currentStage = this.STAGES.EXPORT;
            });
            
            // Listen for Git operation completion
            window.addEventListener('git-operation-completed', (event) => {
                if (event.detail.operation === 'push') {
                    console.log('push-completed event received:', event.detail);
                    this.stageResults.PUSH = { status: 'completed' };
                    this.currentStage = this.STAGES.PUSH;
                }
            });
        },

        isStageCompleted(stage) {
            return this.stageResults[stage] !== null;
        },

        canStartStage(stage) {
            switch (stage) {
                case this.STAGES.EXPORT:
                    return true;

                case this.STAGES.PUSH:
                    // Push should always be available
                    return true;

                default:
                    return false;
            }
        },

        getExportTaskComponent() {
            return this.exportTaskComponentInstance;
        },

        handleExport() {
            this.transitionWorkflowStage(this.STAGES.EXPORT);
        },

        handlePush() {
            window.dispatchEvent(new CustomEvent('workflow-push-clicked'));
            console.log('workflow-push-clicked event dispatched');
        },

        transitionWorkflowStage(newStage) {
            if (!this.canStartStage(newStage)) return;
            
            switch (newStage) {
                case this.STAGES.EXPORT:
                    // Check if export is already in progress
                    if (this.exportTaskComponentInstance.exportStatus === 'running') {
                        console.log('Export already in progress, ignoring transition request');
                        return;
                    }

                    // If we're starting from the beginning, or a button is clicked again while on the same stage, (re)start the actual task
                    if (this.currentStage === this.STAGES.NONE || this.currentStage === this.STAGES.EXPORT) {
                        this.stageResults = {
                            EXPORT: null,
                            PUSH: null
                        };

                        window.dispatchEvent(new CustomEvent('start-export', {
                            detail: { timestamp: Date.now() }
                        }));
                    }

                    // Show the export component
                    this.currentStage = this.STAGES.EXPORT;
                    break;
            }
        }
    };
} 