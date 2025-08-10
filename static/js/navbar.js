// Navbar functionality for Bootstrap templates

// Refresh data function
function refreshData() {
    console.log('Refreshing data...');
    
    // Show loading state
    const refreshBtn = document.querySelector('a[onclick="refreshData()"]');
    if (refreshBtn) {
        const originalHtml = refreshBtn.innerHTML;
        refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Refreshing...';
        refreshBtn.classList.add('disabled');
        
        // Call API
        fetch('/api/refresh-data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            console.log('Refresh response:', data);
            
            // Show success toast
            showToast('Data refreshed successfully!', 'success');
            
            // Restore button
            refreshBtn.innerHTML = originalHtml;
            refreshBtn.classList.remove('disabled');
            
            // Trigger page refresh if on dashboard
            if (window.location.pathname === '/' && typeof refreshAll === 'function') {
                refreshAll();
            }
        })
        .catch(error => {
            console.error('Refresh error:', error);
            showToast('Failed to refresh data', 'error');
            
            // Restore button
            refreshBtn.innerHTML = originalHtml;
            refreshBtn.classList.remove('disabled');
        });
    }
}

// Export data function
function exportData() {
    console.log('Exporting data...');
    
    fetch('/api/export-data')
        .then(response => response.json())
        .then(data => {
            console.log('Export response:', data);
            showToast('Export functionality coming soon!', 'info');
        })
        .catch(error => {
            console.error('Export error:', error);
            showToast('Export failed', 'error');
        });
}

// Show settings modal
function showSettings() {
    console.log('Showing settings...');
    
    // Create settings modal if it doesn't exist
    let settingsModal = document.getElementById('settingsModal');
    if (!settingsModal) {
        const modalHtml = `
            <div class="modal fade" id="settingsModal" tabindex="-1" aria-labelledby="settingsModalLabel" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content bg-dark text-light">
                        <div class="modal-header bg-primary">
                            <h5 class="modal-title" id="settingsModalLabel">
                                <i class="fas fa-cog me-2"></i>Settings
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <label class="form-label">Theme</label>
                                <select class="form-select bg-secondary text-light">
                                    <option value="dark">Dark Theme</option>
                                    <option value="light">Light Theme</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Auto-refresh interval</label>
                                <select class="form-select bg-secondary text-light">
                                    <option value="30">30 seconds</option>
                                    <option value="60" selected>1 minute</option>
                                    <option value="300">5 minutes</option>
                                </select>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="enableNotifications" checked>
                                <label class="form-check-label" for="enableNotifications">
                                    Enable notifications
                                </label>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                            <button type="button" class="btn btn-primary" onclick="saveSettings()">Save Changes</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        settingsModal = document.getElementById('settingsModal');
    }
    
    // Show the modal
    const modal = new bootstrap.Modal(settingsModal);
    modal.show();
}

// Save settings
function saveSettings() {
    console.log('Saving settings...');
    
    fetch('/api/settings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            theme: document.querySelector('#settingsModal select').value,
            // Add other settings here
        })
    })
    .then(response => response.json())
    .then(data => {
        console.log('Settings saved:', data);
        showToast('Settings saved successfully!', 'success');
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('settingsModal'));
        modal.hide();
    })
    .catch(error => {
        console.error('Settings save error:', error);
        showToast('Failed to save settings', 'error');
    });
}

// Connection status monitoring
function updateConnectionStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            const statusElement = document.getElementById('connection-status');
            if (statusElement) {
                if (data.status === 'online') {
                    statusElement.className = 'badge bg-success';
                    statusElement.innerHTML = '<i class="fas fa-circle me-1"></i>Connected';
                } else {
                    statusElement.className = 'badge bg-danger';
                    statusElement.innerHTML = '<i class="fas fa-circle me-1"></i>Disconnected';
                }
            }
        })
        .catch(error => {
            console.error('Status check error:', error);
            const statusElement = document.getElementById('connection-status');
            if (statusElement) {
                statusElement.className = 'badge bg-warning';
                statusElement.innerHTML = '<i class="fas fa-circle me-1"></i>Unknown';
            }
        });
}

// Toast notification helper
function showToast(message, type = 'info') {
    const toastContainer = getOrCreateToastContainer();
    
    const bgClass = type === 'success' ? 'bg-success' : 
                   type === 'error' ? 'bg-danger' : 
                   type === 'warning' ? 'bg-warning' : 'bg-info';
    
    const icon = type === 'success' ? 'check' : 
                type === 'error' ? 'exclamation-triangle' : 
                type === 'warning' ? 'exclamation-triangle' : 'info-circle';
    
    const toastHtml = `
        <div class="toast align-items-center text-white ${bgClass} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas fa-${icon} me-2"></i>${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    const toastElement = toastContainer.lastElementChild;
    const toast = new bootstrap.Toast(toastElement, {
        autohide: true,
        delay: 3000
    });
    
    toast.show();
    
    // Remove toast element after it's hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

// Get or create toast container
function getOrCreateToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }
    return container;
}

// Initialize navbar functionality when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Update connection status immediately and then every 30 seconds
    updateConnectionStatus();
    setInterval(updateConnectionStatus, 30000);
    
    // Update current time in footer if element exists
    function updateFooterTime() {
        const timeElement = document.getElementById('current-time');
        if (timeElement) {
            timeElement.textContent = new Date().toLocaleString();
        }
    }
    
    updateFooterTime();
    setInterval(updateFooterTime, 1000);
});