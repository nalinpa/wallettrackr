class FastAPIAnalysisConsole {
    constructor() {
        this.console = document.getElementById('console');
        this.runButton = document.getElementById('runAnalysis');
        this.networkSelect = document.getElementById('networkSelect');
        this.walletsInput = document.getElementById('walletsInput');
        this.daysInput = document.getElementById('daysInput');
        this.analysisTypeSelect = document.getElementById('analysisTypeSelect');
        this.isRunning = false;
        this.eventSource = null;
        
        this.init();
    }
    
    init() {
        if (this.runButton) {
            this.runButton.addEventListener('click', () => this.startAnalysis());
        }
        
        // Add some default values if inputs exist
        if (this.walletsInput && !this.walletsInput.value) {
            this.walletsInput.value = '173';
        }
        if (this.daysInput && !this.daysInput.value) {
            this.daysInput.value = '1.0';
        }
        
        this.log('💡 FastAPI Analysis Console Ready', 'info');
        this.log('📡 Select network and parameters, then click "Run Analysis"', 'info');
    }
    
    startAnalysis() {
        if (this.isRunning) {
            this.stopAnalysis();
            return;
        }
        
        // Get parameters
        const network = this.networkSelect?.value || 'ethereum';
        const wallets = this.walletsInput?.value || '173';
        const days = this.daysInput?.value || '1.0';
        const analysisType = this.analysisTypeSelect?.value || 'buy';
        
        // Validate parameters
        if (parseInt(wallets) < 1 || parseInt(wallets) > 500) {
            this.log('❌ Wallets must be between 1 and 500', 'error');
            return;
        }
        
        if (parseFloat(days) < 0.1 || parseFloat(days) > 7.0) {
            this.log('❌ Days must be between 0.1 and 7.0', 'error');
            return;
        }
        
        this.log(`🚀 Starting ${analysisType} analysis for ${network}...`, 'info');
        this.log(`📊 Parameters: ${wallets} wallets, ${days} days`, 'info');
        
        // Update UI
        this.setRunning(true);
        
        // Build streaming URL for FastAPI
        const streamUrl = `/api/${network}/${analysisType}/stream?wallets=${wallets}&days=${days}&use_cache=true`;
        
        this.log(`📡 Connecting to: ${streamUrl}`, 'debug');
        
        // Start EventSource connection
        this.eventSource = new EventSource(streamUrl);
        
        this.eventSource.onopen = () => {
            this.log('✅ Connected to analysis stream', 'success');
        };
        
        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleStreamData(data);
            } catch (error) {
                this.log(`❌ Parse error: ${error.message}`, 'error');
                console.error('Stream parse error:', error, event.data);
            }
        };
        
        this.eventSource.onerror = (error) => {
            this.log('❌ Stream connection error', 'error');
            console.error('EventSource error:', error);
            this.setRunning(false);
        };
    }
    
    handleStreamData(data) {
        const { type, processed, total, percentage, message, wallet_address, purchases_found, error } = data;
        
        switch (type) {
            case 'progress':
                if (message) {
                    this.log(`⏳ ${message}`, 'info');
                }
                if (processed !== undefined && total !== undefined) {
                    this.log(`📊 Progress: ${processed}/${total} (${percentage || 0}%)`, 'progress');
                }
                if (wallet_address) {
                    this.log(`🔍 Processing: ${wallet_address.substring(0, 8)}... (${purchases_found || 0} purchases)`, 'debug');
                }
                break;
                
            case 'results':
                this.log('📋 Analysis complete! Processing results...', 'success');
                this.displayResults(data.data);
                break;
                
            case 'complete':
                this.log('✅ Analysis finished successfully', 'success');
                this.setRunning(false);
                break;
                
            case 'error':
                this.log(`❌ Error: ${error || 'Unknown error'}`, 'error');
                this.setRunning(false);
                break;
                
            default:
                this.log(`📡 Received: ${JSON.stringify(data)}`, 'debug');
        }
    }
    
    displayResults(results) {
        if (!results) {
            this.log('⚠️ No results data received', 'warning');
            return;
        }
        
        const { 
            status, 
            network, 
            analysis_type, 
            total_purchases, 
            total_sells, 
            unique_tokens, 
            total_eth_spent, 
            total_estimated_eth,
            top_tokens, 
            analysis_time_seconds,
            from_cache,
            orjson_enabled
        } = results;
        
        // Display summary
        this.log('', 'separator');
        this.log('📊 ANALYSIS RESULTS', 'header');
        this.log('', 'separator');
        
        this.log(`🌐 Network: ${network?.toUpperCase()}`, 'info');
        this.log(`📈 Type: ${analysis_type?.toUpperCase()}`, 'info');
        
        if (analysis_type === 'buy') {
            this.log(`💰 Total Purchases: ${total_purchases || 0}`, 'info');
            this.log(`💎 ETH Spent: ${total_eth_spent?.toFixed(4) || '0.0000'} ETH`, 'info');
        } else {
            this.log(`📉 Total Sells: ${total_sells || 0}`, 'info');
            this.log(`💰 ETH Value: ${total_estimated_eth?.toFixed(4) || '0.0000'} ETH`, 'info');
        }
        
        this.log(`🪙 Unique Tokens: ${unique_tokens || 0}`, 'info');
        this.log(`⏱️ Analysis Time: ${analysis_time_seconds?.toFixed(2) || '0'}s`, 'info');
        
        if (from_cache) {
            this.log(`📋 Source: Cached (fast)`, 'cache');
        } else {
            this.log(`🔄 Source: Fresh analysis`, 'info');
        }
        
        if (orjson_enabled) {
            this.log(`⚡ JSON Optimization: orjson enabled`, 'info');
        }
        
        // Display top tokens
        if (top_tokens && top_tokens.length > 0) {
            this.log('', 'separator');
            this.log('🏆 TOP TOKENS', 'header');
            this.log('', 'separator');
            
            top_tokens.slice(0, 10).forEach((token) => {
                const score = analysis_type === 'buy' ? token.enhanced_alpha_score : token.sell_score;
                const ethValue = analysis_type === 'buy' ? token.total_eth_spent : token.total_estimated_eth;
                
                this.log(`${token.rank}. ${token.token}`, 'token');
                this.log(`   Score: ${score?.toFixed(1) || '0.0'} | Wallets: ${token.wallet_count || 0} | ETH: ${ethValue?.toFixed(4) || '0.0000'}`, 'token-detail');
                
                if (token.platforms?.length > 0) {
                    this.log(`   Platforms: ${token.platforms.join(', ')}`, 'token-detail');
                }
                
                if (token.is_base_native) {
                    this.log(`   🔷 Base Native Token`, 'token-detail');
                }
            });
        } else {
            this.log('⚠️ No tokens found in analysis', 'warning');
        }
        
        this.log('', 'separator');
        this.log('✅ Analysis display complete', 'success');
    }
    
    stopAnalysis() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.setRunning(false);
        this.log('🛑 Analysis stopped by user', 'warning');
    }
    
    setRunning(running) {
        this.isRunning = running;
        if (this.runButton) {
            this.runButton.textContent = running ? 'Stop Analysis' : 'Run Analysis';
            this.runButton.className = running ? 'btn btn-danger' : 'btn btn-primary';
        }
        
        // Disable/enable form inputs
        [this.networkSelect, this.walletsInput, this.daysInput, this.analysisTypeSelect].forEach(input => {
            if (input) {
                input.disabled = running;
            }
        });
    }
    
    log(message, type = 'info') {
        if (!this.console) return;
        
        const timestamp = new Date().toLocaleTimeString();
        const div = document.createElement('div');
        div.className = `console-line console-${type}`;
        
        // Style different message types
        const styles = {
            'info': 'color: #17a2b8;',
            'success': 'color: #28a745; font-weight: bold;',
            'error': 'color: #dc3545; font-weight: bold;',
            'warning': 'color: #ffc107; font-weight: bold;',
            'debug': 'color: #6c757d; font-size: 0.9em;',
            'progress': 'color: #007bff;',
            'header': 'color: #343a40; font-weight: bold; font-size: 1.1em;',
            'separator': 'border-bottom: 1px solid #dee2e6; margin: 5px 0;',
            'token': 'color: #495057; font-weight: bold; margin-left: 10px;',
            'token-detail': 'color: #6c757d; margin-left: 20px; font-size: 0.9em;',
            'cache': 'color: #6f42c1; font-weight: bold;'
        };
        
        if (type === 'separator') {
            div.style.cssText = styles[type];
            div.innerHTML = '&nbsp;';
        } else {
            div.style.cssText = styles[type] || styles['info'];
            div.innerHTML = `<span class="timestamp">[${timestamp}]</span> ${message}`;
        }
        
        this.console.appendChild(div);
        this.console.scrollTop = this.console.scrollHeight;
        
        // Keep console size manageable
        const lines = this.console.children;
        if (lines.length > 500) {
            for (let i = 0; i < 100; i++) {
                if (lines[0]) {
                    this.console.removeChild(lines[0]);
                }
            }
        }
    }
    
    clearConsole() {
        if (this.console) {
            this.console.innerHTML = '';
            this.log('🧹 Console cleared', 'info');
        }
    }
}

// Enhanced API status checker for dashboard
class APIStatusChecker {
    constructor() {
        this.statusInterval = null;
        this.init();
    }
    
    init() {
        this.checkStatus();
        this.startPeriodicCheck();
    }
    
    async checkStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            this.updateStatusDisplay(data);
        } catch (error) {
            console.error('Status check failed:', error);
            this.updateStatusDisplay(null, error);
        }
    }
    
    updateStatusDisplay(data, error = null) {
        const statusElement = document.getElementById('apiStatus');
        const cacheElement = document.getElementById('cacheStatus');
        
        if (error || !data) {
            if (statusElement) {
                statusElement.innerHTML = '<span class="badge badge-danger">API Offline</span>';
            }
            return;
        }
        
        // Update API status
        if (statusElement) {
            const status = data.status === 'online' ? 'success' : 'warning';
            statusElement.innerHTML = `
                <span class="badge badge-${status}">API ${data.status}</span>
                <small class="text-muted ml-2">v${data.version}</small>
            `;
        }
        
        // Update cache status
        if (cacheElement && data.cache) {
            const cacheInfo = data.cache;
            const hitRate = cacheInfo.hit_rate || '0%';
            const entries = cacheInfo.entries || 0;
            const orjson = cacheInfo.orjson_enabled ? '⚡' : '';
            
            cacheElement.innerHTML = `
                <span class="badge badge-info">Cache: ${entries} entries</span>
                <small class="text-muted ml-2">${hitRate} hit rate ${orjson}</small>
            `;
        }
    }
    
    startPeriodicCheck() {
        // Check status every 30 seconds
        this.statusInterval = setInterval(() => {
            this.checkStatus();
        }, 3000000);
    }
    
    stopPeriodicCheck() {
        if (this.statusInterval) {
            clearInterval(this.statusInterval);
            this.statusInterval = null;
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Initializing FastAPI Dashboard...');
    
    // Initialize analysis console
    window.analysisConsole = new FastAPIAnalysisConsole();
    
    // Initialize status checker
    window.statusChecker = new APIStatusChecker();
    
    // Add clear console button functionality
    const clearButton = document.getElementById('clearConsole');
    if (clearButton) {
        clearButton.addEventListener('click', () => {
            window.analysisConsole.clearConsole();
        });
    }
    
    console.log('✅ FastAPI Dashboard initialized');
});

// Export for debugging
window.FastAPIAnalysisConsole = FastAPIAnalysisConsole;
window.APIStatusChecker = APIStatusChecker;