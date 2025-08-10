// Monitor JavaScript for Real-time Crypto Alpha Analysis

class Monitor {
    constructor() {
        this.eventSource = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.activityCount = 0;
        this.alertCount = 0;
    }

    init() {
        this.setupEventListeners();
        this.updateConnectionStatus();
    }

    setupEventListeners() {
        // Auto-scroll toggle
        $('#auto-scroll').change((e) => {
            this.autoScroll = e.target.checked;
        });

        // Monitor control buttons
        $('#start-monitoring').click(() => this.startMonitoring());
        $('#stop-monitoring').click(() => this.stopMonitoring());
        $('#clear-logs').click(() => this.clearActivityFeed());
    }

    connectToSSE() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        this.showConnectionModal();

        try {
            this.eventSource = new EventSource('/api/stream');
            
            this.eventSource.onopen = () => {
                console.log('SSE connection opened');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateConnectionStatus();
                this.hideConnectionModal();
                this.addActivityItem('Connected to real-time feed', 'success');
            };

            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleSSEData(data);
                } catch (error) {
                    console.error('Error parsing SSE data:', error);
                }
            };

            this.eventSource.onerror = (error) => {
                console.error('SSE connection error:', error);
                this.isConnected = false;
                this.updateConnectionStatus();
                this.hideConnectionModal();
                
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    this.addActivityItem(`Connection lost. Reconnecting... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`, 'warning');
                    
                    setTimeout(() => {
                        this.connectToSSE();
                    }, this.reconnectDelay * this.reconnectAttempts);
                } else {
                    this.addActivityItem('Connection failed. Please refresh the page.', 'error');
                }
            };

        } catch (error) {
            console.error('Failed to create SSE connection:', error);
            this.hideConnectionModal();
            this.addActivityItem('Failed to establish connection', 'error');
        }
    }

    handleSSEData(data) {
        switch (data.type) {
            case 'transaction':
                this.handleTransactionData(data);
                break;
            case 'alert':
                this.handleAlertData(data);
                break;
            case 'wallet_update':
                this.handleWalletUpdate(data);
                break;
            case 'system':
                this.handleSystemMessage(data);
                break;
            default:
                console.log('Unknown SSE data type:', data.type);
        }
    }

    handleTransactionData(data) {
        const transaction = data.transaction;
        const wallet = data.wallet;
        
        this.addActivityItem(
            `New transaction detected for ${wallet.substring(0, 10)}...`,
            'info',
            {
                details: `${transaction.value} ETH - ${transaction.type}`,
                hash: transaction.hash,
                timestamp: data.timestamp
            }
        );

        // Update wallet in monitored table if visible
        this.updateMonitoredWalletRow(wallet, data);
    }

    handleAlertData(data) {
        const alert = data.alert;
        
        this.addActivityItem(
            alert.message,
            alert.priority,
            {
                wallet: alert.wallet,
                details: alert.details,
                timestamp: data.timestamp
            }
        );

        this.addAlertToSidebar(alert);
        this.updateAlertCount();
    }

    handleWalletUpdate(data) {
        const wallet = data.wallet;
        
        this.addActivityItem(
            `Wallet ${wallet.address.substring(0, 10)}... updated`,
            'info',
            {
                details: `Balance: ${wallet.balance} ETH`,
                timestamp: data.timestamp
            }
        );

        this.updateMonitoredWalletRow(wallet.address, data);
    }

    handleSystemMessage(data) {
        this.addActivityItem(data.message, 'info', {
            timestamp: data.timestamp
        });
    }

    addActivityItem(message, type = 'info', details = {}) {
        const feed = $('#activity-feed');
        const timestamp = details.timestamp || new Date().toLocaleTimeString();
        const iconClass = this.getActivityIcon(type);
        const textClass = this.getActivityTextClass(type);

        const activityHtml = `
            <div class="activity-item p-3 border-bottom new" data-type="${type}">
                <div class="d-flex align-items-start">
                    <div class="me-3">
                        <i class="${iconClass} ${textClass}"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <p class="mb-1">${message}</p>
                                ${details.details ? `<small class="text-muted">${details.details}</small>` : ''}
                            </div>
                            <small class="text-muted timestamp">${timestamp}</small>
                        </div>
                        ${details.hash ? `
                            <div class="mt-2">
                                <a href="https://etherscan.io/tx/${details.hash}" target="_blank" class="btn btn-sm btn-outline-info">
                                    <i class="fas fa-external-link-alt me-1"></i>View on Etherscan
                                </a>
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;

        feed.prepend(activityHtml);
        this.activityCount++;

        // Remove 'new' class after animation
        setTimeout(() => {
            feed.find('.activity-item.new').removeClass('new');
        }, 500);

        // Auto-scroll if enabled
        if ($('#auto-scroll').is(':checked')) {
            feed.scrollTop(0);
        }

        // Limit items to prevent memory issues
        const items = feed.find('.activity-item');
        if (items.length > 100) {
            items.slice(100).remove();
        }
    }

    addAlertToSidebar(alert) {
        const sidebar = $('#alerts-sidebar');
        const timestamp = new Date().toLocaleTimeString();
        const priorityClass = alert.priority === 'high' ? 'danger' : 
                             alert.priority === 'medium' ? 'warning' : 'info';

        const alertHtml = `
            <div class="alert-item p-3 border-bottom alert-${alert.priority} new">
                <div class="d-flex align-items-start">
                    <div class="flex-grow-1">
                        <h6 class="mb-1">${alert.title || 'Alert'}</h6>
                        <p class="mb-1 small">${alert.message}</p>
                        <small class="text-muted">
                            <i class="fas fa-clock me-1"></i>
                            ${timestamp}
                        </small>
                    </div>
                    <span class="badge bg-${priorityClass}">
                        ${alert.priority.charAt(0).toUpperCase() + alert.priority.slice(1)}
                    </span>
                </div>
            </div>
        `;

        sidebar.prepend(alertHtml);
        this.alertCount++;

        // Remove 'new' class after animation
        setTimeout(() => {
            sidebar.find('.alert-item.new').removeClass('new');
        }, 500);

        // Limit alerts
        const alerts = sidebar.find('.alert-item');
        if (alerts.length > 50) {
            alerts.slice(50).remove();
        }
    }

    updateMonitoredWalletRow(address, data) {
        const row = $(`tr[data-wallet="${address}"]`);
        if (row.length) {
            // Update last activity
            row.find('td:nth-child(4)').html(`<small>${new Date().toLocaleTimeString()}</small>`);
            
            // Update alert count if provided
            if (data.alert_count !== undefined) {
                row.find('td:nth-child(5)').html(`<span class="badge bg-warning">${data.alert_count}</span>`);
            }
        }
    }

    async startMonitoring() {
        try {
            const response = await fetch('/api/start_monitoring', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            const result = await response.json();

            if (response.ok && result.success) {
                this.showAlert('Monitoring started successfully!', 'success');
                this.connectToSSE();
                
                // Update UI
                $('.btn:contains("Start Monitoring")').removeClass('btn-success').addClass('btn-danger')
                    .html('<i class="fas fa-stop me-2"></i>Stop Monitoring');
                
                // Update status indicator
                $('.status-indicator').removeClass('status-inactive').addClass('status-active');
                
                setTimeout(() => {
                    location.reload(); // Refresh to update server-side state
                }, 1000);
            } else {
                this.showAlert(result.error || 'Failed to start monitoring', 'error');
            }
        } catch (error) {
            console.error('Error starting monitoring:', error);
            this.showAlert('Network error. Please try again.', 'error');
        }
    }

    async stopMonitoring() {
        try {
            const response = await fetch('/api/stop_monitoring', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            const result = await response.json();

            if (response.ok && result.success) {
                this.showAlert('Monitoring stopped', 'info');
                this.disconnectSSE();
                
                // Update UI
                $('.btn:contains("Stop Monitoring")').removeClass('btn-danger').addClass('btn-success')
                    .html('<i class="fas fa-play me-2"></i>Start Monitoring');
                
                // Update status indicator
                $('.status-indicator').removeClass('status-active').addClass('status-inactive');
                
                setTimeout(() => {
                    location.reload(); // Refresh to update server-side state
                }, 1000);
            } else {
                this.showAlert(result.error || 'Failed to stop monitoring', 'error');
            }
        } catch (error) {
            console.error('Error stopping monitoring:', error);
            this.showAlert('Network error. Please try again.', 'error');
        }
    }

    disconnectSSE() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.isConnected = false;
        this.updateConnectionStatus();
        this.addActivityItem('Disconnected from real-time feed', 'warning');
    }

    clearActivityFeed() {
        $('#activity-feed').html(`
            <div class="p-3">
                <div class="text-center text-muted">
                    <i class="fas fa-satellite-dish fa-2x mb-2"></i>
                    <p>Activity feed cleared</p>
                </div>
            </div>
        `);
        this.activityCount = 0;
    }

    updateConnectionStatus() {
        const statusElement = $('#connection-status');
        if (this.isConnected) {
            statusElement.removeClass('bg-danger').addClass('bg-success')
                .html('<i class="fas fa-circle me-1"></i>Connected');
        } else {
            statusElement.removeClass('bg-success').addClass('bg-danger')
                .html('<i class="fas fa-circle me-1"></i>Disconnected');
        }
    }

    updateAlertCount() {
        $('#active-alerts-count').text(this.alertCount);
    }

    getActivityIcon(type) {
        switch (type) {
            case 'success': return 'fas fa-check-circle';
            case 'error': return 'fas fa-exclamation-triangle';
            case 'warning': return 'fas fa-exclamation-circle';
            case 'info': return 'fas fa-info-circle';
            default: return 'fas fa-circle';
        }
    }

    getActivityTextClass(type) {
        switch (type) {
            case 'success': return 'text-success';
            case 'error': return 'text-danger';
            case 'warning': return 'text-warning';
            case 'info': return 'text-info';
            default: return 'text-muted';
        }
    }

    showConnectionModal() {
        $('#connectionModal').modal('show');
    }

    hideConnectionModal() {
        $('#connectionModal').modal('hide');
    }

    showAlert(message, type = 'info') {
        const alertClass = type === 'error' ? 'alert-danger' : 
                          type === 'success' ? 'alert-success' : 
                          type === 'warning' ? 'alert-warning' : 'alert-info';
        
        const iconClass = type === 'error' ? 'fas fa-exclamation-triangle' :
                         type === 'success' ? 'fas fa-check-circle' :
                         type === 'warning' ? 'fas fa-exclamation-circle' : 'fas fa-info-circle';

        const alertHtml = `
            <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
                <i class="${iconClass} me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;

        $('#dynamic-alerts').prepend(alertHtml);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            $('#dynamic-alerts .alert:last-child').fadeOut('slow', function() {
                $(this).remove();
            });
        }, 5000);
    }

    removeFromMonitoring(address) {
        if (confirm(`Remove ${address.substring(0, 10)}... from monitoring?`)) {
            // Implementation for removing from monitoring
            this.showAlert('Wallet removed from monitoring', 'info');
        }
    }
}

// Global monitor instance
let monitor;

// Initialize monitor when document is ready
function initializeMonitor() {
    monitor = new Monitor();
    monitor.init();
}

// Global functions for onclick events
function connectToSSE() {
    monitor.connectToSSE();
}

function startMonitoring() {
    monitor.startMonitoring();
}

function stopMonitoring() {
    monitor.stopMonitoring();
}

function clearLogs() {
    monitor.clearActivityFeed();
}

function removeFromMonitoring(address) {
    monitor.removeFromMonitoring(address);
}