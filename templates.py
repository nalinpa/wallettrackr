HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Alpha Analysis Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #2d1b69 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            text-align: center;
            margin-bottom: 30px;
            padding: 30px;
            background: linear-gradient(135deg, #ff4757, #ff6b7a);
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(255, 71, 87, 0.3);
        }

        .header h1 {
            font-size: 2.5rem;
            font-weight: 800;
            margin-bottom: 10px;
        }

        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }

        /* Console Output Dialog Styles */
        .overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            z-index: 9998;
            backdrop-filter: blur(5px);
        }

        .overlay.active {
            display: block;
        }

        .console-dialog {
            display: none;
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 90%;
            max-width: 800px;
            max-height: 80vh;
            background: linear-gradient(145deg, #1e1e3a, #2a2a5a);
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            z-index: 9999;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .console-dialog.active {
            display: block;
            animation: slideIn 0.3s ease-out;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translate(-50%, -60%);
            }
            to {
                opacity: 1;
                transform: translate(-50%, -50%);
            }
        }

        .console-header {
            background: linear-gradient(135deg, #667eea, #764ba2);
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .console-title {
            font-size: 1.2rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .console-title .spinner {
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .console-content {
            height: 400px;
            overflow-y: auto;
            padding: 20px;
            background: #0a0a0a;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            line-height: 1.6;
        }

        .console-line {
            margin-bottom: 8px;
            padding: 4px 8px;
            border-radius: 4px;
            transition: background 0.2s;
        }

        .console-line:hover {
            background: rgba(255, 255, 255, 0.05);
        }

        .console-line.info {
            color: #4fc3f7;
        }

        .console-line.success {
            color: #66bb6a;
        }

        .console-line.warning {
            color: #ffa726;
        }

        .console-line.error {
            color: #ef5350;
        }

        .console-line.highlight {
            color: #ab47bc;
            font-weight: bold;
        }

        .console-line .timestamp {
            color: #757575;
            margin-right: 10px;
        }

        .console-line .emoji {
            margin-right: 8px;
        }

        .console-footer {
            padding: 15px 20px;
            background: rgba(0, 0, 0, 0.3);
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .progress-bar {
            flex-grow: 1;
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            overflow: hidden;
            margin-right: 20px;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 4px;
            transition: width 0.3s ease;
            width: 0%;
        }

        .close-console {
            background: rgba(255, 255, 255, 0.1);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.2);
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .close-console:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        /* Rest of existing styles */
        .controls {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }

        .btn {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
        }

        .btn.active {
            background: linear-gradient(135deg, #ff4757, #ff6b7a);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: linear-gradient(145deg, #2c2c54, #40407a);
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
        }

        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            color: #ffa726;
            margin-bottom: 10px;
        }

        .stat-label {
            font-size: 0.9rem;
            color: #b0b0b0;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .section {
            background: linear-gradient(145deg, #1e1e3a, #2a2a5a);
            margin-bottom: 30px;
            border-radius: 15px;
            padding: 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
        }

        .section-title {
            font-size: 1.8rem;
            font-weight: 700;
            margin-bottom: 25px;
            color: #ffa726;
        }

        .token-list {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .token-item {
            background: linear-gradient(135deg, #2c2c54, #3c3c6e);
            padding: 20px;
            border-radius: 12px;
            border-left: 4px solid #ff4757;
            transition: all 0.3s ease;
        }

        .token-item:hover {
            transform: translateX(10px);
        }

        .token-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            flex-wrap: wrap;
            gap: 15px;
        }

        .token-name {
            font-size: 1.4rem;
            font-weight: 700;
            color: #ffa726;
        }

        .token-score {
            background: linear-gradient(135deg, #ff4757, #ff6b7a);
            color: white;
            padding: 8px 15px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9rem;
        }

        .token-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }

        .detail-item {
            text-align: center;
            padding: 12px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
        }

        .detail-value {
            font-size: 1.1rem;
            font-weight: 700;
            color: #4fc3f7;
            margin-bottom: 5px;
        }

        .detail-label {
            font-size: 0.8rem;
            color: #b0b0b0;
            text-transform: uppercase;
        }

        .contract-address {
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            background: rgba(0, 0, 0, 0.3);
            padding: 8px;
            border-radius: 6px;
            word-break: break-all;
        }

        .loading {
            text-align: center;
            padding: 50px;
            font-size: 1.2rem;
        }

        .error {
            background: linear-gradient(135deg, #e74c3c, #c0392b);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }

        .native-flag {
            display: inline-block;
            margin-right: 8px;
            font-size: 1.2rem;
        }

        .platform-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }

        .platform-tag {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .status-indicator {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 20px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9rem;
            z-index: 1000;
        }

        .status-online {
            background: linear-gradient(135deg, #2ed573, #7bed9f);
            color: white;
        }

        .status-loading {
            background: linear-gradient(135deg, #ffa726, #ffcc02);
            color: white;
        }

        .status-error {
            background: linear-gradient(135deg, #ff4757, #ff6b7a);
            color: white;
        }

        @media (max-width: 768px) {
            .header h1 {
                font-size: 2rem;
            }
            
            .token-header {
                flex-direction: column;
                align-items: flex-start;
            }
            
            .controls {
                flex-direction: column;
                align-items: center;
            }

            .console-dialog {
                width: 95%;
                max-height: 90vh;
            }
        }
    </style>
</head>
<body>
    <div class="status-indicator" id="status-indicator">🟢 Online</div>
    
    <!-- Console Output Dialog -->
    <div class="overlay" id="overlay"></div>
    <div class="console-dialog" id="console-dialog">
        <div class="console-header">
            <div class="console-title">
                <div class="spinner"></div>
                <span>Analysis Console Output</span>
            </div>
        </div>
        <div class="console-content" id="console-content">
            <!-- Console output will be added here -->
        </div>
        <div class="console-footer">
            <div class="progress-bar">
                <div class="progress-fill" id="progress-fill"></div>
            </div>
            <button class="close-console" onclick="closeConsole()">Close</button>
        </div>
    </div>
    
    <div class="container">
        <div class="header">
            <h1>🚀 Crypto Alpha Analysis Dashboard</h1>
            <p>Real-time tracking of smart wallet activity across Ethereum and Base networks</p>
        </div>

        <div class="controls">
            <button class="btn active" onclick="loadData('eth', 'buy')">ETH Buys</button>
            <button class="btn" onclick="loadData('eth', 'sell')">ETH Sells</button>
            <button class="btn" onclick="loadData('base', 'buy')">Base Buys</button>
            <button class="btn" onclick="loadData('base', 'sell')">Base Sells</button>
            <button class="btn" onclick="refreshAll()">🔄 Refresh All</button>
        </div>

        <div id="stats-container">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" id="total-activity">-</div>
                    <div class="stat-label">Total Activity</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="unique-tokens">-</div>
                    <div class="stat-label">Unique Tokens</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="total-value">-</div>
                    <div class="stat-label">Total Value (ETH)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="last-updated">-</div>
                    <div class="stat-label">Last Updated</div>
                </div>
            </div>
        </div>

        <div id="content-container">
            <div class="loading">Ready to analyze...</div>
        </div>
    </div>

    <script>
        let currentNetwork = 'eth';
        let currentType = 'buy';
        let eventSource = null;

        function showConsole() {
            document.getElementById('overlay').classList.add('active');
            document.getElementById('console-dialog').classList.add('active');
            document.getElementById('console-content').innerHTML = '';
            document.getElementById('progress-fill').style.width = '0%';
        }

        function closeConsole() {
            document.getElementById('overlay').classList.remove('active');
            document.getElementById('console-dialog').classList.remove('active');
            
            // Make sure to close any active SSE connection
            if (eventSource) {
                console.log('Closing SSE connection from closeConsole');
                eventSource.close();
                eventSource = null;
            }
        }
        
        window.addEventListener('beforeunload', function() {
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
        });

        function addConsoleOutput(message, type = 'info') {
            const consoleContent = document.getElementById('console-content');
            const line = document.createElement('div');
            line.className = `console-line ${type}`;
            
            const timestamp = new Date().toLocaleTimeString();
            line.innerHTML = `<span class="timestamp">[${timestamp}]</span>${message}`;
            
            consoleContent.appendChild(line);
            consoleContent.scrollTop = consoleContent.scrollHeight;
        }

        function updateProgress(percentage) {
            document.getElementById('progress-fill').style.width = percentage + '%';
        }

        function updateStatus(status, message) {
            const indicator = document.getElementById('status-indicator');
            indicator.className = 'status-indicator status-' + status;
            indicator.innerHTML = message;
        }

        function loadData(network, type) {
            currentNetwork = network;
            currentType = type;
            console.log(`Loading data for ${network} ${type}...`);
            
            // Update button states
            document.querySelectorAll('.btn').forEach(btn => btn.classList.remove('active'));
            if (event && event.target) {
                event.target.classList.add('active');
            }
            
            // Show console and loading
            showConsole();
            document.getElementById('content-container').innerHTML = '<div class="loading">Analyzing data...</div>';
            updateStatus('loading', '🔄 Loading...');
            
            // Add initial console output
            addConsoleOutput(`<span class="emoji">🚀</span> Starting ${network.toUpperCase()} ${type} analysis...`, 'highlight');
            
            // Close any existing SSE connection
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            
            // Check if server supports SSE for real-time updates
            if (typeof(EventSource) !== "undefined") {
                // Try to connect to SSE endpoint for real-time console output
                const streamUrl = `/api/${network}/${type}/stream`;
                console.log('Connecting to SSE:', streamUrl);
                
                eventSource = new EventSource(streamUrl);
                
                let hasReceivedData = false;
                let isComplete = false;
                
                eventSource.onmessage = function(event) {
                    hasReceivedData = true;
                    try {
                        const data = JSON.parse(event.data);
                        
                        if (data.type === 'console') {
                            console.log(data.message);
                            addConsoleOutput(data.message, data.level || 'info');
                        } else if (data.type === 'progress') {
                            console.log('Progress update:', data.percentage);
                            updateProgress(data.percentage);
                        } else if (data.type === 'results') {
                            // Handle the results data
                            console.log('Received results data:', data.data);
                            addConsoleOutput('📊 Processing results data...', 'success');
                            
                            // Display the results immediately
                            displayResultData(data.data, currentNetwork, currentType);

                        } else if (data.type === 'complete' || data.type === 'final_complete') {
                            if (!isComplete) {
                                isComplete = true;
                                console.log('Analysis complete, closing SSE connection');
                                
                                // Close the EventSource
                                eventSource.close();
                                eventSource = null;
                                
                                // Add completion message
                                addConsoleOutput('✅ Analysis complete!', 'success');
                                console.log('Final data:', data);
                                
                                // Wait a moment then close console and fetch results
                                setTimeout(() => {
                                    closeConsole();
                                    updateStatus('online', '🟢 Online');
                                }, 1500);
                            }
                        }
                    } catch (error) {
                        console.error('Error parsing SSE data:', error);
                        addConsoleOutput(`<span class="emoji">❌</span> Error: ${error.message}`, 'error');
                        showError(error.message);
                        updateStatus('error', '❌ Error');
                    }
                };
                
                eventSource.onerror = function(error) {
                    console.log('SSE error or connection closed');
                    
                    // Close the connection
                    if (eventSource) {
                        eventSource.close();
                        eventSource = null;
                    }
                    
                    // If we haven't received any data, fall back to regular fetch
                    if (!hasReceivedData && !isComplete) {
                        console.log('Data not received');
                        addConsoleOutput('❌ Error: Unable to connect to SSE stream. Please try again later.');
                    } else if (!isComplete) {                        
                        console.log('Incomplete scan');
                        addConsoleOutput('❌ Error: Unable to connect to SSE stream. Please try again later.');
                        setTimeout(() => {
                            closeConsole();
                        }, 1000);
                    }
                };
                
                // Set a timeout to close the connection if it takes too long
                setTimeout(() => {
                    if (eventSource && !isComplete) {
                        console.log('SSE timeout, closing connection');
                        eventSource.close();
                        eventSource = null;
                        closeConsole();
                    }
                }, 900000); // 15 min timeout

            } else {
                console.log('SSE not supported');
            }
        }

        function displayResultData(data, network, type) {
            console.log('Displaying result data:', data);
            
            // Update stats based on the actual result data
            if (type === 'buy') {
                document.getElementById('total-activity').textContent = data.total_purchases || 0;
                document.getElementById('total-value').textContent = (data.total_eth_spent || 0).toFixed(4);
            } else {
                document.getElementById('total-activity').textContent = data.total_sells || 0;
                document.getElementById('total-value').textContent = (data.total_estimated_eth || 0).toFixed(4);
            }
            
            document.getElementById('unique-tokens').textContent = data.unique_tokens || 0;
            document.getElementById('last-updated').textContent = data.last_updated ? 
                new Date(data.last_updated).toLocaleTimeString() : new Date().toLocaleTimeString();

            // Build content
            let html = '';
            
            if (!data.top_tokens || data.top_tokens.length === 0) {
                html = `<div class="section">
                    <div class="section-title">ℹ️ No Significant Activity Found</div>
                    <p>${data.message || 'No tokens met the criteria for display'}</p>
                </div>`;
            } else {
                const networkName = network.toUpperCase();
                const typeName = type === 'buy' ? 'Alpha Tokens' : 'Sell Pressure';
                const scoreLabel = type === 'buy' ? 'Alpha Score' : 'Sell Score';
                
                html = `<div class="section">
                    <div class="section-title">🏆 Top ${networkName} ${typeName}</div>
                    <div class="token-list">`;
                
                data.top_tokens.forEach(token => {
                    const nativeFlag = token.is_base_native ? '<span class="native-flag">🔵</span>' : '';
                    const valueKey = type === 'buy' ? 'total_eth_spent' : 'total_estimated_eth';
                    const scoreKey = type === 'buy' ? 'alpha_score' : 'sell_score';
                    
                    const platforms = token.platforms || token.methods || [];
                    const platformTags = platforms.slice(0, 3).map(p => 
                        `<span class="platform-tag">${p}</span>`
                    ).join('');
                    
                    // Ensure we have valid values
                    const ethValue = token[valueKey] || 0;
                    const score = token[scoreKey] || 0;
                    
                    html += `
                        <div class="token-item">
                            <div class="token-header">
                                <div class="token-name">${nativeFlag}${token.token}</div>
                                <div class="token-score">${scoreLabel}: ${score}</div>
                            </div>
                            <div class="token-details">
                                <div class="detail-item">
                                    <div class="detail-value">#${token.rank}</div>
                                    <div class="detail-label">Rank</div>
                                </div>
                                <div class="detail-item">
                                    <div class="detail-value">${token.wallet_count || 0}</div>
                                    <div class="detail-label">Wallets</div>
                                </div>
                                <div class="detail-item">
                                    <div class="detail-value">${ethValue.toFixed(4)}</div>
                                    <div class="detail-label">ETH Value</div>
                                </div>
                                <div class="detail-item">
                                    <div class="detail-value">${token.avg_wallet_score || 0}</div>
                                    <div class="detail-label">Avg Score</div>
                                </div>
                            </div>
                            <div class="detail-item" style="margin-top: 10px;">
                                <div class="detail-value contract-address">
                                    ${token.contract_address || 'N/A'}
                                </div>
                                <div class="detail-label">Contract Address</div>
                            </div>
                            <div class="platform-tags">
                                ${platformTags}
                            </div>
                        </div>
                    `;
                });
                
                html += '</div></div>';
            }
            
            document.getElementById('content-container').innerHTML = html;
        }

        // Function to show no data message
        function showNoData(network, type) {
            const networkName = network.toUpperCase();
            const typeName = type === 'buy' ? 'Buy Activity' : 'Sell Activity';
            
            document.getElementById('content-container').innerHTML = `
                <div class="section">
                    <div class="section-title">ℹ️ No ${networkName} ${typeName} Found</div>
                    <p>The analysis completed but no significant activity was detected in the specified timeframe.</p>
                </div>
            `;
            
            // Reset stats to 0
            document.getElementById('total-activity').textContent = '0';
            document.getElementById('unique-tokens').textContent = '0';
            document.getElementById('total-value').textContent = '0.0000';
            document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
        }

        function showError(message) {
            document.getElementById('content-container').innerHTML = 
                `<div class="error">❌ Error: ${message}</div>`;
        }

        function refreshAll() {
            loadData(currentNetwork, currentType);
        }

        // Add keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey || e.metaKey) {
                switch(e.key) {
                    case '1':
                        e.preventDefault();
                        loadData('eth', 'buy');
                        break;
                    case '2':
                        e.preventDefault();
                        loadData('eth', 'sell');
                        break;
                    case '3':
                        e.preventDefault();
                        loadData('base', 'buy');
                        break;
                    case '4':
                        e.preventDefault();
                        loadData('base', 'sell');
                        break;
                    case 'r':
                        e.preventDefault();
                        refreshAll();
                        break;
                }
            }
        });

        // Close console on ESC key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                closeConsole();
            }
        });
    </script>
</body>
</html>
'''