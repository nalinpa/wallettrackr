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
        }
    </style>
</head>
<body>
    <div class="status-indicator" id="status-indicator">🟢 Online</div>
    
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
            <div class="loading">Loading data...</div>
        </div>
    </div>

    <script>
        let currentNetwork = 'eth';
        let currentType = 'buy';

        function updateStatus(status, message) {
            const indicator = document.getElementById('status-indicator');
            indicator.className = 'status-indicator status-' + status;
            indicator.innerHTML = message;
        }

        function loadData(network, type) {
            currentNetwork = network;
            currentType = type;
            
            // Update button states
            document.querySelectorAll('.btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            // Show loading
            document.getElementById('content-container').innerHTML = '<div class="loading">Loading data...</div>';
            updateStatus('loading', '🔄 Loading...');
            
            // Fetch data
            fetch(`/api/${network}/${type}`)
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        showError(data.error);
                        updateStatus('error', '❌ Error');
                    } else {
                        displayData(data, network, type);
                        updateStatus('online', '🟢 Online');
                    }
                })
                .catch(error => {
                    showError('Failed to fetch data: ' + error.message);
                    updateStatus('error', '❌ Error');
                });
        }

        function displayData(data, network, type) {
            // Update stats
            if (type === 'buy') {
                document.getElementById('total-activity').textContent = data.total_purchases || 0;
                document.getElementById('total-value').textContent = (data.total_eth_spent || 0).toFixed(4);
            } else {
                document.getElementById('total-activity').textContent = data.total_sells || 0;
                document.getElementById('total-value').textContent = (data.total_estimated_eth || 0).toFixed(4);
            }
            
            document.getElementById('unique-tokens').textContent = data.unique_tokens || 0;
            document.getElementById('last-updated').textContent = data.last_updated ? 
                new Date(data.last_updated).toLocaleTimeString() : '-';

            // Build content
            let html = '';
            
            if (data.status === 'no_data') {
                html = `<div class="section">
                    <div class="section-title">ℹ️ No Data Found</div>
                    <p>${data.message}</p>
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
                    
                    html += `
                        <div class="token-item">
                            <div class="token-header">
                                <div class="token-name">${nativeFlag}${token.token}</div>
                                <div class="token-score">${scoreLabel}: ${token[scoreKey]}</div>
                            </div>
                            <div class="token-details">
                                <div class="detail-item">
                                    <div class="detail-value">#${token.rank}</div>
                                    <div class="detail-label">Rank</div>
                                </div>
                                <div class="detail-item">
                                    <div class="detail-value">${token.wallet_count}</div>
                                    <div class="detail-label">Wallets</div>
                                </div>
                                <div class="detail-item">
                                    <div class="detail-value">${token[valueKey].toFixed(4)}</div>
                                    <div class="detail-label">ETH Value</div>
                                </div>
                                <div class="detail-item">
                                    <div class="detail-value">${token.avg_wallet_score}</div>
                                    <div class="detail-label">Avg Score</div>
                                </div>
                            </div>
                            <div class="detail-item" style="margin-top: 10px;">
                                <div class="detail-value contract-address">
                                    ${token.contract_address}
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

        function showError(message) {
            document.getElementById('content-container').innerHTML = 
                `<div class="error">❌ Error: ${message}</div>`;
        }

        function refreshAll() {
            loadData(currentNetwork, currentType);
        }

        // Load initial data
        loadData('eth', 'buy');

        // Auto-refresh every 5 minutes
        setInterval(() => {
            loadData(currentNetwork, currentType);
        }, 300000);

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
    </script>
</body>
</html>
'''