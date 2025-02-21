window.workspaceManager = function() {
    return {
        activeOperation: null,
        syncMode: localStorage.getItem('syncMode') || 'export',
        showGitPopup: false,
        gitAction: null,
        gitUrl: null,
        allowModeToggle: true,
        darkMode: false,

        async init() {
            try {
                const response = await fetch('/api/workspace-info/app-mode');
                const data = await response.json();
                
                const serverMode = data.mode.toLowerCase();
                if (serverMode === 'export') {
                    this.syncMode = 'export';
                    this.allowModeToggle = false;
                } else if (serverMode === 'import') {
                    this.syncMode = 'import';
                    this.allowModeToggle = false;
                }
                // For 'both', keep allowModeToggle true and use saved preference
                
            } catch (error) {
                console.error('Error fetching app mode:', error);
            }

            window.addEventListener('workflow-push-clicked', () => {
                this.handlePush();
            });

            window.addEventListener('workflow-pull-clicked', () => {
                this.handlePull();
            });

            this.initializeButtons();

            // Initialize dark mode
            try {
                const darkModeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
                const shouldUseDarkMode = localStorage.theme === 'dark' || 
                    (!('theme' in localStorage) && darkModeMediaQuery.matches);
                
                this.darkMode = shouldUseDarkMode;
                this.updateTheme();

                // Listen for system dark mode changes
                darkModeMediaQuery.addEventListener('change', (e) => {
                    if (!('theme' in localStorage)) {
                        this.darkMode = e.matches;
                        this.updateTheme();
                    }
                });
            } catch (error) {
                console.warn('Dark mode initialization encountered an error:', error);
            }
        },

        initializeButtons() {
            this.$nextTick(() => {
                document.querySelectorAll('.diagram-button:not([style*="display: none"])').forEach(button => {
                    const x = button.dataset.x;
                    const y = button.dataset.y;
                    const color = button.dataset.color;
                    const width = button.dataset.width;
                    
                    button.style.left = `${x}px`;
                    button.style.top = `${y}px`;
                    button.style.backgroundColor = color;
                    button.style.width = `${width}px`;
                });
            });
        },

        toggleSyncMode() {
            if (!this.allowModeToggle) return;
            this.syncMode = this.syncMode === 'export' ? 'import' : 'export';
            this.activeOperation = null;
            window.dispatchEvent(new Event('collapse-workspace-info'));
            // Use nextTick to ensure DOM updates before initializing buttons
            this.$nextTick(() => {
                this.initializeButtons();
            });
        },

        saveSyncModePreference() {
            localStorage.setItem('syncMode', this.syncMode);
        },
        
        handlePull() {
            console.log('Pull button clicked');
            this.gitAction = 'pull';
            this.showGitPopup = true;
            console.log('State after pull click:', { 
                showGitPopup: this.showGitPopup, 
                gitAction: this.gitAction 
            });
            this.fetchGitUrl();
        },

        handlePush() {
            console.log('Push button clicked');
            this.gitAction = 'push';
            this.showGitPopup = true;
            console.log('State after push click:', { 
                showGitPopup: this.showGitPopup, 
                gitAction: this.gitAction 
            });
            this.fetchGitUrl();
        },

        async fetchGitUrl() {
            console.log('Fetching Git URL...');
            try {
                const response = await fetch('/api/workspace-info/folder');
                const data = await response.json();
                
                // Extract organization ID from the databricks_host
                const orgId = this.extractOrgIdFromHost(data.databricks_host);
                
                // Ensure we're using just the Databricks host part
                const databricksHost = this.extractDatabricksHost(data.databricks_host);
                this.gitUrl = `${databricksHost}/browse/folders/${data.folder_id}${orgId ? `?o=${orgId}` : ''}`;
                console.log('Git URL set:', this.gitUrl);
            } catch (error) {
                console.error('Failed to fetch Git URL:', error);
            }
        },

        extractDatabricksHost(url) {
            try {
                // If the URL contains 'databricksapps.com', extract the actual Databricks host
                if (url.includes('databricksapps.com')) {
                    const match = url.match(/\/([^\/]+\.azuredatabricks\.net)/);
                    if (match) {
                        return `https://${match[1]}`;
                    }
                }
                // If it's already a Databricks host, ensure it has https://
                return url.startsWith('https://') ? url : `https://${url}`;
            } catch (error) {
                console.error('Error extracting Databricks host:', error);
                return url;
            }
        },

        extractOrgIdFromHost(host) {
            // For Azure Databricks
            const azureMatch = host.match(/adb-(\d+)/);
            if (azureMatch) {
                return azureMatch[1];
            }
            
            // For AWS Databricks
            const awsMatch = host.match(/dbc-[a-z0-9]+-[a-z0-9]+/);
            if (awsMatch) {
                return null; // AWS typically doesn't use the ?o= parameter
            }
            
            return null;
        },

        closeGitPopup() {
            this.showGitPopup = false;
            this.gitAction = null;
            this.gitUrl = null;
        },

        openInDatabricks() {
            if (this.gitUrl) {
                window.open(this.gitUrl, '_blank');
                // Dispatch completion event after opening Databricks
                window.dispatchEvent(new CustomEvent('git-operation-completed', {
                    detail: {
                        operation: this.gitAction,
                        status: 'completed'
                    }
                }));
            }
            this.closeGitPopup();
        },

        toggleDarkMode() {
            this.darkMode = !this.darkMode;
            localStorage.theme = this.darkMode ? 'dark' : 'light';
            this.updateTheme();
        },

        updateTheme() {
            if (this.darkMode) {
                document.documentElement.classList.add('dark');
            } else {
                document.documentElement.classList.remove('dark');
            }
        },
    };
} 