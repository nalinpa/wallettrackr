// Dashboard JavaScript for Crypto Alpha Analysis

class Dashboard {
    constructor() {
        this.refreshInterval = null;
        this.isLoading = false;
    }

    init() {
        this.setupEventListeners();
        this.loadWalletData();
        this.startAutoRefresh();
    }

    setupEventListeners() {
        // Add wallet form
        $('#add-wallet-form').on('submit', (e) => {
            e.preventDefault();
            this.addWallet();
        });

        // View mode toggle
        $('input[name="view-mode"]').change((e) => {
            this.toggleViewMode(e.target.id);
        });

        // Global refresh button
        $('#refresh-all').click(() => {
            this.refreshAll();
        });
    }

    async addWallet() {
        const address = $('#wallet-address').val().trim();
        const network = $('#wallet-network').val();

        if (!address) {
            this.showAlert('Please enter a wallet address', 'warning');
            return;
        }

        if (!this.isValidAddress(address)) {
            this.showAlert('Please enter a valid wallet address', 'error');
            return;
        }

        this.setLoading(true);

        try {
            const response = await fetch('/api/add_wallet', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    address: address,
                    network: network
                })
            });

            const result = await response.json();

            if (response.ok && result.success) {
                this.showAlert('Wallet added successfully!', 'success');
                $('#wallet-address').val('');
                await this.loadWalletData();
            } else {
                this.showAlert(result.error || 'Failed to add wallet', 'error');
            }
        } catch (error) {
            console.error('Error adding wallet:', error);
            this.showAlert('Network error. Please try again.', 'error');
        } finally {
            this.setLoading(false);
        }
    }

    async removeWallet(address) {
        if (!confirm(`Are you sure you want to remove wallet ${address.substring(0, 10)}...?`)) {
            return;
        }

        this.setLoading(true);

        try {
            const response = await fetch('/api/remove_wallet', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ address: address })
            });

            const result = await response.json();

            if (response.ok && result.success) {
                this.showAlert('Wallet removed successfully!', 'success');
                await this.loadWalletData();
            } else {
                this.showAlert(result.error || 'Failed to remove wallet', 'error');
            }
        } catch (error) {
            console.error('Error removing wallet:', error);
            this.showAlert('Network error. Please try again.', 'error');
        } finally {
            this.setLoading(false);
        }
    }

    async refreshWallet(address) {
        this.setLoading(true);
        
        try {
            const response = await fetch(`/api/wallet/${address}/refresh`, {
                method: 'POST'
            });

            const result = await response.json();

            if (response.ok && result.success) {
                this.showAlert('Wallet data refreshed!', 'success');
                await this.loadWalletData();
            } else {
                this.showAlert(result.error || 'Failed to refresh wallet', 'error');
            }
        } catch (error) {
            console.error('Error refreshing wallet:', error);
            this.showAlert('Network error. Please try again.', 'error');
        } finally {
            this.setLoading(false);
        }
    }

    async loadWalletData() {
        this.setLoading(true);

        try {
            const response = await fetch('/api/wallets');
            const data = await response.json();

            if (response.ok) {
                this.renderWallets(data.wallets);
                this.updateStats(data.wallets);
            } else {
                console.error('Failed to load wallet data:', data.error);
                this.showAlert('Failed to load wallet data', 'error');
            }
        } catch (error) {
            console.error('Error loading wallets:', error);
            this.showAlert('Network error loading wallets', 'error');
        } finally {
            this.setLoading(false);
        }
    }

    renderWallets(wallets) {
        const container = $('#wallets-container');
        
        if (!wallets || wallets.length === 0) {
            container.html(`
                <div class="col-12">
                    <div class="card">
                        <div class="card-body text-center py-5">
                            <i class="fas fa-wallet fa-3x text-muted mb-3"></i>
                            <h5>No wallets tracked yet</h5>
                            <p class="text-muted">Add your first wallet address above to start tracking alpha opportunities.</p>
                        </div>
                    </div>
                </div>
            `);
            return;
        }

        const walletsHtml = wallets.map(wallet => this.renderWalletCard(wallet)).join('');
        container.html(walletsHtml);
    }

    renderWalletCard(wallet) {
        const profitClass = wallet.profit_24h > 0 ? 'profit-positive' : 'profit-negative';
        const statusBadge = wallet.is_active ? 'bg-success">Active' : 'bg-secondary">Inactive';
        const networkBadge = this.getNetworkBadge(wallet.network);

        return `
        <div class="col-lg-4 col-md-6 mb-4">
            <div class="card wallet-card h-100" data-wallet="${wallet.address}">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h6 class="mb-0">
                        <i class="fas fa-wallet me-2"></i>
                        ${wallet.address.substring(0, 8)}...${wallet.address.substring(wallet.address.length - 6)}
                    </h6>
                    <div class="dropdown">
                        <button class="btn btn-sm btn-outline-secondary" type="button" data-bs-toggle="dropdown">
                            <i class="fas fa-ellipsis-v"></i>
                        </button>
                        <ul class="dropdown-menu dropdown-menu-dark">
                            <li><a class="dropdown-item" href="#" onclick="dashboard.viewWalletDetails('${wallet.address}')">
                                <i class="fas fa-eye me-2"></i>View Details
                            </a></li>
                            <li><a class="dropdown-item" href="#" onclick="dashboard.refreshWallet('${wallet.address}')">
                                <i class="fas fa-sync me-2"></i>Refresh
                            </a></li>
                            <li><a class="dropdown-item" href="${wallet.etherscan_url || '#'}" target="_blank">
                                <i class="fas fa-external-link-alt me-2"></i>Etherscan
                            </a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item text-danger" href="#" onclick="dashboard.removeWallet('${wallet.address}')">
                                <i class="fas fa-trash me-2"></i>Remove
                            </a></li>
                        </ul>
                    </div>
                </div>
                
                <div class="card-body">
                    <div class="mb-2">
                        <span class="badge ${networkBadge}">${wallet.network ? wallet.network.charAt(0).toUpperCase() + wallet.network.slice(1) : 'Unknown'}</span>
                        <span class="badge ${statusBadge}</span>
                    </div>
                    
                    <div class="mb-3">
                        <small class="text-muted">ETH Balance</small>
                        <h5 class="mb-1">
                            ${wallet.balance ? parseFloat(wallet.balance).toFixed(4) + ' ETH' : '<span class="text-muted">Loading...</span>'}
                        </h5>
                        ${wallet.balance_usd ? `<small class="text-success">${parseFloat(wallet.balance_usd).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</small>` : ''}
                    </div>
                    
                    <div class="mb-3">
                        <small class="text-muted">Recent Transactions</small>
                        <div class="mt-1">
                            ${wallet.recent_transactions ? `<small class="text-info">${wallet.recent_transactions} in 24h</small>` : '<small class="text-muted">No recent activity</small>'}
                        </div>
                    </div>
                    
                    ${wallet.alpha_score ? `
                    <div class="mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <small class="text-muted">Alpha Score</small>
                            <span class="badge bg-${wallet.alpha_score > 70 ? 'success' : wallet.alpha_score > 40 ? 'warning' : 'danger'}">
                                ${wallet.alpha_score}/100
                            </span>
                        </div>
                        <div class="progress mt-1" style="height: 4px;">
                            <div class="progress-bar bg-${wallet.alpha_score > 70 ? 'success' : wallet.alpha_score > 40 ? 'warning' : 'danger'}" 
                                 style="width: ${wallet.alpha_score}%"></div>
                        </div>
                    </div>
                    ` : ''}
                    
                    <div class="text-end">
                        <small class="text-muted">
                            <i class="fas fa-clock me-1"></i>
                            Updated ${wallet.last_updated || 'never'}
                        </small>
                    </div>
                </div>
                
                <div class="card-footer bg-transparent">
                    <div class="btn-group w-100" role="group">
                        <button type="button" class="btn btn-sm btn-outline-primary" 
                                onclick="dashboard.startMonitoring('${wallet.address}')">
                            <i class="fas fa-play me-1"></i>Monitor
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-info" 
                                onclick="dashboard.viewTransactions('${wallet.address}')">
                            <i class="fas fa-list me-1"></i>Transactions
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-success" 
                                onclick="dashboard.analyzeWallet('${wallet.address}')">
                            <i class="fas fa-chart-bar me-1"></i>Analyze
                        </button>
                    </div>
                </div>
            </div>
        </div>
        `;
    }

    getNetworkBadge(network) {
        switch(network) {
            case 'ethereum': return 'bg-primary';
            case 'base': return 'bg-info';
            case 'arbitrum': return 'bg-warning';
            default: return 'bg-secondary';
        }
    }

    updateStats(wallets) {
        $('#total-wallets').text(wallets ? wallets.length : 0);
        
        const activeWallets = wallets ? wallets.filter(w => w.is_active).length : 0;
        $('#active-monitors').text(activeWallets);
        
        $('#last-update').text(new Date().toLocaleString());
    }

    async startMonitoring(address) {
        try {
            const response = await fetch('/api/start_monitoring', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ address: address })
            });

            const result = await response.json();

            if (response.ok && result.success) {
                this.showAlert('Monitoring started!', 'success');
                await this.loadWalletData();
            } else {
                this.showAlert(result.error || 'Failed to start monitoring', 'error');
            }
        } catch (error) {
            console.error('Error starting monitoring:', error);
            this.showAlert('Network error. Please try again.', 'error');
        }
    }

    viewWalletDetails(address) {
        window.location.href = `/wallet/${address}`;
    }

    viewTransactions(address) {
        // Open transactions in new tab/modal
        const url = `https://etherscan.io/address/${address}`;
        window.open(url, '_blank');
    }

    analyzeWallet(address) {
        // Future feature - wallet analysis
        this.showAlert('Wallet analysis feature coming soon!', 'info');
    }

    toggleViewMode(mode) {
        const container = $('#wallets-container');
        if (mode === 'list-view') {
            container.removeClass('row').addClass('list-group');
            // Convert cards to list items
        } else {
            container.removeClass('list-group').addClass('row');
            // Convert back to grid
        }
    }

    refreshAll() {
        this.loadWalletData();
        this.showAlert('Refreshing all data...', 'info');
    }

    startAutoRefresh() {
        // Auto-refresh every 30 seconds
        this.refreshInterval = setInterval(() => {
            this.loadWalletData();
        }, 30000);
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    setLoading(loading) {
        this.isLoading = loading;
        const spinner = $('#loading-spinner');
        
        if (loading) {
            spinner.show();
        } else {
            spinner.hide();
        }
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

    isValidAddress(address) {
        // Basic Ethereum address validation
        return /^0x[a-fA-F0-9]{40}$/.test(address);
    }
}

// Global dashboard instance
let dashboard;

// Initialize dashboard when document is ready
function initializeDashboard() {
    dashboard = new Dashboard();
    dashboard.init();
}

// Global functions for onclick events
function refreshData() {
    dashboard.refreshAll();
}

function exportData() {
    // Future feature
    dashboard.showAlert('Export feature coming soon!', 'info');
}

function showSettings() {
    // Future feature
    dashboard.showAlert('Settings panel coming soon!', 'info');
}