from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
import logging
import json

# Import your existing analysis components
try:
    from core.analysis.buy_analyzer import BuyAnalyzer
    from core.analysis.sell_analyzer import SellAnalyzer
    from services.blockchain.alchemy_client import AlchemyClient
    ANALYSIS_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Analysis components not available: {e}")
    ANALYSIS_AVAILABLE = False

# Import existing monitor if available
try:
    from auto_monitor import monitor
    MONITOR_AVAILABLE = True
except ImportError:
    MONITOR_AVAILABLE = False

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitoring"])

try:
    from services.notifications import telegram_client, send_alert_notifications, check_notification_config
    NOTIFICATIONS_AVAILABLE = True
    logger.info("✅ Telegram notifications available")
except ImportError as e:
    NOTIFICATIONS_AVAILABLE = False
    logger.warning(f"⚠️ Telegram notifications not available: {e}")
    
# Pydantic models for request bodies
class MonitorConfig(BaseModel):
    check_interval_minutes: int = 60
    networks: List[str] = ["base"]
    num_wallets: int = 50
    use_interval_for_timeframe: bool = True

class AlertThresholds(BaseModel):
    min_wallets: int = 2
    min_eth_total: float = 0.5
    min_alpha_score: float = 30.0
    min_sell_score: float = 25.0
    min_transactions: int = 3
    filter_stablecoins: bool = True

# In-memory storage for monitor state
monitor_state = {
    "is_running": False,
    "last_check": None,
    "next_check": None,
    "current_check": None,
    "config": {
        "check_interval_minutes": 60,
        "networks": ["base"],
        "num_wallets": 50,
        "use_interval_for_timeframe": True
    },
    "alert_thresholds": {
        "min_wallets": 2,
        "min_eth_total": 0.5,
        "min_alpha_score": 30.0,
        "min_sell_score": 25.0,
        "min_transactions": 3,
        "filter_stablecoins": True
    },
    "stats": {
        "total_alerts": 0,
        "known_tokens": 0,
        "total_checks": 0,
        "last_check_duration": 0
    },
    "alerts": [],
    "last_results": None
}

# Background monitoring task
monitoring_task = None

@router.get("/monitor/status", response_model=Dict[str, Any])
async def get_monitor_status():
    """Get monitoring system status - ENHANCED WITH NOTIFICATION STATUS"""
    try:
        # Check if we have analysis capabilities
        capabilities = {
            "analysis_available": ANALYSIS_AVAILABLE,
            "monitor_available": MONITOR_AVAILABLE,
            "notifications_available": NOTIFICATIONS_AVAILABLE,
            "networks_supported": monitor_state["config"]["networks"]
        }
        
        # Add notification status details
        notification_status = {
            "available": NOTIFICATIONS_AVAILABLE,
            "configured": False,
            "last_test": None
        }
        
        if NOTIFICATIONS_AVAILABLE:
            try:
                from services.notifications import check_notification_config, telegram_client
                notification_status["configured"] = check_notification_config()
                notification_status["bot_token_set"] = bool(telegram_client.bot_token)
                notification_status["chat_id_set"] = bool(telegram_client.chat_id)
            except Exception as e:
                logger.debug(f"Error checking notification status: {e}")
        
        # Merge capabilities with state
        status_data = {
            **monitor_state, 
            "capabilities": capabilities,
            "notifications": notification_status
        }
        
        # If external monitor is available, merge its status too
        if MONITOR_AVAILABLE:
            try:
                external_status = monitor.get_status()
                status_data = {**status_data, **external_status}
            except Exception as e:
                logger.warning(f"Could not get external monitor status: {e}")
        
        return {"status": "success", "data": status_data}
        
    except Exception as e:
        logger.error(f"Error getting monitor status: {e}")
        return {
            "status": "error", 
            "data": {**monitor_state, "error": str(e)}
        }

@router.post("/monitor/start")
async def start_monitor():
    """Start the monitoring system"""
    global monitor_state, monitoring_task
    
    if monitor_state["is_running"]:
        return {
            "status": "info",
            "message": "Monitor is already running",
            "config": monitor_state["config"]
        }
    
    try:
        # Start the monitoring loop
        monitor_state["is_running"] = True
        monitor_state["last_check"] = datetime.now().isoformat()
        
        # Calculate next check time
        next_check = datetime.now() + timedelta(minutes=monitor_state["config"]["check_interval_minutes"])
        monitor_state["next_check"] = next_check.isoformat()
        
        # Start background monitoring task
        monitoring_task = asyncio.create_task(monitoring_loop())
        
        # Also start external monitor if available
        external_result = None
        if MONITOR_AVAILABLE:
            try:
                external_result = monitor.start_monitoring()
            except Exception as e:
                logger.warning(f"External monitor start failed: {e}")
        
        return {
            "status": "success",
            "message": f"Monitor started with {len(monitor_state['config']['networks'])} networks",
            "config": monitor_state["config"],
            "external_monitor": external_result
        }
        
    except Exception as e:
        monitor_state["is_running"] = False
        logger.error(f"Error starting monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/monitor/stop")
async def stop_monitor():
    """Stop the monitoring system"""
    global monitor_state, monitoring_task
    
    try:
        # Stop monitoring loop
        monitor_state["is_running"] = False
        monitor_state["next_check"] = None
        monitor_state["current_check"] = None
        
        # Cancel background task
        if monitoring_task and not monitoring_task.done():
            monitoring_task.cancel()
            try:
                await monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop external monitor if available
        external_result = None
        if MONITOR_AVAILABLE:
            try:
                external_result = monitor.stop_monitoring()
            except Exception as e:
                logger.warning(f"External monitor stop failed: {e}")
        
        return {
            "status": "success",
            "message": "Monitor stopped",
            "external_monitor": external_result
        }
        
    except Exception as e:
        logger.error(f"Error stopping monitor: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/monitor/check-now")
async def check_now(background_tasks: BackgroundTasks):
    """Run an immediate check"""
    if monitor_state["current_check"]:
        return {
            "status": "info",
            "message": "A check is already in progress",
            "current_check": monitor_state["current_check"]
        }
    
    try:
        # Run check in background
        background_tasks.add_task(run_analysis_check, immediate=True)
        
        monitor_state["current_check"] = {
            "started": datetime.now().isoformat(),
            "type": "immediate",
            "networks": monitor_state["config"]["networks"]
        }
        
        return {
            "status": "success",
            "message": "Immediate analysis started",
            "check_info": monitor_state["current_check"]
        }
        
    except Exception as e:
        logger.error(f"Error running immediate check: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monitor/test")
async def test_connection():
    """Test monitor connections and capabilities - ENHANCED WITH NOTIFICATION TEST"""
    results = {}
    
    try:
        # Test analysis components
        results["analysis_components"] = ANALYSIS_AVAILABLE
        
        # Test external monitor
        results["external_monitor"] = MONITOR_AVAILABLE
        
        # Test notifications
        results["notifications_available"] = NOTIFICATIONS_AVAILABLE
        
        if NOTIFICATIONS_AVAILABLE:
            try:
                from services.notifications import check_notification_config, telegram_client
                results["notification_config"] = check_notification_config()
                
                # Test Telegram connection
                async with telegram_client:
                    connection_ok = await telegram_client.test_connection()
                    results["telegram_connection"] = connection_ok
                    
            except Exception as e:
                logger.error(f"Notification test failed: {e}")
                results["telegram_connection"] = False
                results["notification_error"] = str(e)
        
        # Test network connections for each configured network
        network_tests = {}
        for network in monitor_state["config"]["networks"]:
            try:
                async with AlchemyClient(network) as client:
                    connection_ok = await client.test_connection()
                    network_tests[network] = connection_ok
            except Exception as e:
                logger.error(f"Network test failed for {network}: {e}")
                network_tests[network] = False
        
        results["networks"] = network_tests
        
        # Test analyzer initialization
        analyzer_tests = {}
        if ANALYSIS_AVAILABLE:
            for network in monitor_state["config"]["networks"]:
                try:
                    # Test buy analyzer
                    async with BuyAnalyzer(network) as analyzer:
                        analyzer_tests[f"{network}_buy_analyzer"] = True
                    
                    # Test sell analyzer
                    async with SellAnalyzer(network) as analyzer:
                        analyzer_tests[f"{network}_sell_analyzer"] = True
                        
                except Exception as e:
                    logger.error(f"Analyzer test failed for {network}: {e}")
                    analyzer_tests[f"{network}_analyzers"] = False
        
        results["analyzers"] = analyzer_tests
        
        # Overall health check
        critical_systems = [
            results["analysis_components"],
            all(network_tests.values()),
            (not analyzer_tests or all(analyzer_tests.values()))
        ]
        
        notification_ok = results.get("telegram_connection", False) if NOTIFICATIONS_AVAILABLE else True
        
        all_critical_passed = all(critical_systems)
        
        return {
            "status": "success" if all_critical_passed else "partial",
            "results": results,
            "summary": f"Critical systems: {'✅ PASS' if all_critical_passed else '❌ FAIL'}, "
                      f"Notifications: {'✅ OK' if notification_ok else '⚠️ CHECK CONFIG'}"
        }
        
    except Exception as e:
        logger.error(f"Error in connection test: {e}")
        return {
            "status": "error",
            "results": {"error": str(e)},
            "summary": "❌ Test failed with error"
        }
        
@router.post("/monitor/config")
async def update_config(config: MonitorConfig):
    """Update monitor configuration"""
    global monitor_state
    
    try:
        old_config = monitor_state["config"].copy()
        monitor_state["config"] = config.dict()
        
        # Validate networks
        supported_networks = ["ethereum", "base"]
        invalid_networks = [n for n in config.networks if n not in supported_networks]
        if invalid_networks:
            monitor_state["config"] = old_config  # Revert
            raise ValueError(f"Unsupported networks: {invalid_networks}. Supported: {supported_networks}")
        
        # Update next check time if monitor is running
        if monitor_state["is_running"]:
            next_check = datetime.now() + timedelta(minutes=config.check_interval_minutes)
            monitor_state["next_check"] = next_check.isoformat()
        
        # Update external monitor config if available
        if MONITOR_AVAILABLE:
            try:
                # Update external monitor config here
                pass
            except Exception as e:
                logger.warning(f"Could not update external monitor config: {e}")
        
        return {
            "status": "success",
            "message": f"Configuration updated for {len(config.networks)} networks",
            "config": monitor_state["config"],
            "changes": {
                "networks": old_config["networks"] != config.networks,
                "interval": old_config["check_interval_minutes"] != config.check_interval_minutes,
                "wallets": old_config["num_wallets"] != config.num_wallets
            }
        }
        
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/monitor/thresholds")
async def update_thresholds(thresholds: AlertThresholds):
    """Update alert thresholds"""
    global monitor_state
    
    try:
        old_thresholds = monitor_state["alert_thresholds"].copy()
        monitor_state["alert_thresholds"] = thresholds.dict()
        
        return {
            "status": "success",
            "message": "Alert thresholds updated",
            "thresholds": monitor_state["alert_thresholds"],
            "changes": {k: old_thresholds[k] != thresholds.dict()[k] for k in thresholds.dict().keys()}
        }
        
    except Exception as e:
        logger.error(f"Error updating thresholds: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monitor/live-updates")
async def get_live_updates():
    """Get recent updates for live monitoring"""
    try:
        return {
            "current_check": monitor_state.get("current_check"),
            "last_check": monitor_state.get("last_check"),
            "next_check": monitor_state.get("next_check"),
            "is_running": monitor_state.get("is_running", False),
            "stats": monitor_state.get("stats", {}),
            "recent_alerts": monitor_state["alerts"][-5:] if monitor_state["alerts"] else []
        }
    except Exception as e:
        logger.error(f"Error getting live updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monitor/alerts")
async def get_alerts(limit: int = 20, offset: int = 0):
    """Get recent alerts"""
    try:
        # Get alerts from our state (sorted by newest first)
        all_alerts = sorted(monitor_state["alerts"], key=lambda x: x["timestamp"], reverse=True)
        
        # Apply pagination
        paginated_alerts = all_alerts[offset:offset+limit]
        
        # Return just the array of alerts (not wrapped in an object)
        # This matches what the frontend JavaScript expects
        return paginated_alerts
        
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/monitor/test-notifications")
async def test_notifications():
    """Test the notification system"""
    try:
        if not NOTIFICATIONS_AVAILABLE:
            return {
                "status": "error",
                "message": "Notifications not available",
                "details": "Check if services.notifications is properly configured"
            }
        
        # Check configuration
        from services.notifications import check_notification_config, send_test_notification
        
        config_ok = check_notification_config()
        if not config_ok:
            return {
                "status": "error", 
                "message": "Telegram configuration invalid",
                "details": "Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables"
            }
        
        # Send test notification
        success = await send_test_notification()
        
        if success:
            return {
                "status": "success",
                "message": "Test notification sent successfully",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "error",
                "message": "Test notification failed",
                "details": "Check server logs for specific error details"
            }
            
    except Exception as e:
        logger.error(f"❌ Test notification failed: {e}")
        return {
            "status": "error",
            "message": f"Test notification error: {str(e)}",
            "details": "Check server logs for full error details"
        }
        
# Background monitoring loop
async def monitoring_loop():
    """Main monitoring loop that runs periodic checks"""
    logger.info("🔄 Monitoring loop started")
    
    while monitor_state["is_running"]:
        try:
            # Wait until next check time
            now = datetime.now()
            next_check_time = datetime.fromisoformat(monitor_state["next_check"])
            
            if now >= next_check_time:
                logger.info("⏰ Scheduled check time reached, running analysis...")
                await run_analysis_check(immediate=False)
                
                # Schedule next check
                next_check = now + timedelta(minutes=monitor_state["config"]["check_interval_minutes"])
                monitor_state["next_check"] = next_check.isoformat()
            
            # Sleep for a short interval before checking again
            await asyncio.sleep(30)  # Check every 30 seconds
            
        except asyncio.CancelledError:
            logger.info("🛑 Monitoring loop cancelled")
            break
        except Exception as e:
            logger.error(f"❌ Error in monitoring loop: {e}")
            await asyncio.sleep(60)  # Wait a minute before retrying

def debug_ranked_tokens_structure(results, analysis_type: str):
    """Debug function to understand ranked_tokens data structure"""
    if not hasattr(results, 'ranked_tokens') or not results.ranked_tokens:
        logger.info(f"No ranked_tokens to debug for {analysis_type}")
        return
    
    logger.info(f"🔍 Debugging {analysis_type} ranked_tokens structure:")
    
    for i, token_tuple in enumerate(results.ranked_tokens[:3]):  # Check first 3
        try:
            if len(token_tuple) >= 3:
                token_name, token_info, score_value = token_tuple
                
                logger.info(f"  Token {i+1}: {token_name}")
                logger.info(f"    Score/ETH parameter: {score_value} (type: {type(score_value)})")
                
                if isinstance(token_info, dict):
                    logger.info(f"    Token info keys: {list(token_info.keys())}")
                    
                    # Check for ETH value fields
                    eth_fields = ['total_eth_spent', 'total_estimated_eth', 'total_eth_value']
                    for field in eth_fields:
                        if field in token_info:
                            value = token_info[field]
                            logger.info(f"    {field}: {value} (type: {type(value)})")
                            
                            # Check if it looks like wei
                            if isinstance(value, (int, float)) and value > 1000000000000000000:
                                converted = value / 1e18
                                logger.info(f"      → Converted from wei: {converted}")
                else:
                    logger.info(f"    Token info type: {type(token_info)}, value: {token_info}")
                    
        except Exception as e:
            logger.error(f"Error debugging token {i}: {e}")
            
# Main analysis function
async def run_analysis_check(immediate: bool = False):
    """Run the actual analysis check using your analyzers - ENHANCED WITH NOTIFICATIONS"""
    global monitor_state
    
    if not ANALYSIS_AVAILABLE:
        logger.warning("⚠️ Analysis components not available, skipping check")
        return
    
    check_start = datetime.now()
    check_type = "immediate" if immediate else "scheduled"
    
    try:
        logger.info(f"🚀 Starting {check_type} analysis check")
        
        monitor_state["current_check"] = {
            "started": check_start.isoformat(),
            "type": check_type,
            "networks": monitor_state["config"]["networks"],
            "status": "running"
        }
        
        all_results = {}
        new_alerts = []
        
        # Run analysis for each configured network
        for network in monitor_state["config"]["networks"]:
            logger.info(f"📊 Analyzing {network} network...")
            
            network_results = await analyze_network(network)
            all_results[network] = network_results
            
            # Process results and generate alerts
            network_alerts = process_analysis_results(network, network_results)
            new_alerts.extend(network_alerts)
        
        # Update state
        check_duration = (datetime.now() - check_start).total_seconds()
        monitor_state["last_check"] = check_start.isoformat()
        monitor_state["current_check"] = None
        monitor_state["last_results"] = all_results
        monitor_state["stats"]["total_checks"] += 1
        monitor_state["stats"]["last_check_duration"] = check_duration
        
        # Add new alerts
        monitor_state["alerts"].extend(new_alerts)
        monitor_state["stats"]["total_alerts"] += len(new_alerts)
        
        # ENHANCED: Send notifications for new alerts
        if new_alerts:
            logger.info(f"📱 Sending notifications for {len(new_alerts)} new alerts")
            try:
                await send_alert_notifications(new_alerts)
                logger.info("✅ Notifications sent successfully")
            except Exception as notification_error:
                logger.error(f"❌ Failed to send notifications: {notification_error}")
                # Continue execution even if notifications fail
        
        # Keep only last 100 alerts to prevent memory bloat
        if len(monitor_state["alerts"]) > 100:
            monitor_state["alerts"] = monitor_state["alerts"][-100:]
        
        logger.info(f"✅ Analysis complete: {len(new_alerts)} new alerts, {check_duration:.1f}s duration")
        
        # Log summary of findings with correct ETH values
        if new_alerts:
            for alert in new_alerts:
                score = alert['data'].get('alpha_score') or alert['data'].get('sell_score', 0)
                eth_value = alert['data'].get('total_eth_spent') or alert['data'].get('total_eth_value', 0)
                logger.info(f"🚨 {alert['alert_type'].upper()}: {alert['token']} ({alert['network']}) - ETH: {eth_value:.4f}, Score: {score}")
        
    except Exception as e:
        logger.error(f"❌ Analysis check failed: {e}")
        monitor_state["current_check"] = None
        raise

async def analyze_network(network: str):
    """Analyze a specific network for both buy and sell activity"""
    config = monitor_state["config"]
    results = {}
    
    try:
        # Determine timeframe
        if config["use_interval_for_timeframe"] and monitor_state["last_check"]:
            # Use time since last check
            last_check_time = datetime.fromisoformat(monitor_state["last_check"])
            hours_back = (datetime.now() - last_check_time).total_seconds() / 3600
            days_back = max(hours_back / 24, 0.1)  # Minimum 0.1 days
        else:
            # Use default timeframe
            days_back = 1.0
        
        # Run buy analysis
        logger.info(f"🔍 Running buy analysis for {network} ({days_back:.2f} days)")
        async with BuyAnalyzer(network) as buy_analyzer:
            buy_results = await buy_analyzer.analyze_wallets_concurrent(
                num_wallets=config["num_wallets"],
                days_back=days_back
            )
            results["buy_analysis"] = buy_results
        
        # Run sell analysis
        logger.info(f"📉 Running sell analysis for {network} ({days_back:.2f} days)")
        async with SellAnalyzer(network) as sell_analyzer:
            sell_results = await sell_analyzer.analyze_wallets_concurrent(
                num_wallets=config["num_wallets"],
                days_back=days_back
            )
            results["sell_analysis"] = sell_results
        
        logger.info(f"✅ {network} analysis complete")
        return results
        
    except Exception as e:
        logger.error(f"❌ Network analysis failed for {network}: {e}")
        raise

def process_analysis_results(network: str, results: dict) -> List[dict]:
    """Process analysis results and generate alerts based on thresholds"""
    alerts = []
    thresholds = monitor_state["alert_thresholds"]
    
    try:
        logger.info(f"Processing analysis results for {network}")
        logger.debug(f"Results keys: {list(results.keys())}")
        
        # Process buy analysis results
        if "buy_analysis" in results:
            buy_results = results["buy_analysis"]
            logger.info(f"Buy analysis: {buy_results.total_transactions} transactions, {buy_results.unique_tokens} tokens")
            logger.debug(f"Buy ranked tokens count: {len(buy_results.ranked_tokens) if hasattr(buy_results, 'ranked_tokens') else 'N/A'}")
            
            buy_alerts = process_buy_results(network, buy_results, thresholds)
            alerts.extend(buy_alerts)
            logger.info(f"Generated {len(buy_alerts)} buy alerts")
        
        # Process sell analysis results  
        if "sell_analysis" in results:
            sell_results = results["sell_analysis"]
            logger.info(f"Sell analysis: {sell_results.total_transactions} transactions, {sell_results.unique_tokens} tokens")
            logger.debug(f"Sell ranked tokens count: {len(sell_results.ranked_tokens) if hasattr(sell_results, 'ranked_tokens') else 'N/A'}")
            
            sell_alerts = process_sell_results(network, sell_results, thresholds)
            alerts.extend(sell_alerts)
            logger.info(f"Generated {len(sell_alerts)} sell alerts")
        
        return alerts
        
    except Exception as e:
        logger.error(f"Error processing results for {network}: {e}")
        return []

def process_buy_results(network: str, results, thresholds: dict) -> List[dict]:
    """Process buy analysis results and generate alerts - FIXED ETH VALUES"""
    alerts = []
    
    try:
        if not hasattr(results, 'ranked_tokens') or not results.ranked_tokens:
            logger.info(f"No ranked tokens found in buy results for {network}")
            return alerts
        
        logger.info(f"Processing {len(results.ranked_tokens)} buy tokens for {network}")
        
        for token_data in results.ranked_tokens[:10]:  # Check top 10 tokens
            try:
                # Extract data - your ranked_tokens structure is [token_name, token_info, eth_value]
                token_name, token_info, eth_value = token_data
                
                # Debug log the structure
                logger.debug(f"Processing token {token_name}: info type={type(token_info)}, eth_value={eth_value}")
                
                # Handle different token_info structures
                if isinstance(token_info, dict):
                    wallet_count = len(token_info.get('wallets', set()))
                    purchase_count = token_info.get('total_purchases', token_info.get('count', 0))
                    platforms = token_info.get('platforms', [])
                    
                    # FIXED: Get the correct ETH value from token_info, not the score
                    # The eth_value parameter is actually the alpha score, not ETH value!
                    correct_eth_value = token_info.get('total_eth_spent', 0.0)
                    
                    # Validate and convert the ETH value
                    if isinstance(correct_eth_value, (int, float)):
                        # Check if it's in wei format (very large number)
                        if correct_eth_value > 1000000000000000000:  # More than 1 ETH in wei
                            correct_eth_value = correct_eth_value / 1e18
                            logger.debug(f"🔧 Converted ETH from wei: {correct_eth_value}")
                        
                        # Safety cap for unrealistic values
                        if correct_eth_value > 100:  # More than 100 ETH for single alert
                            logger.warning(f"⚠️ Capping high ETH value for {token_name}: {correct_eth_value} -> 10.0")
                            correct_eth_value = 10.0
                    else:
                        correct_eth_value = 0.0
                        
                else:
                    # Fallback if token_info is not a dict
                    wallet_count = 1
                    purchase_count = 1
                    platforms = ['Unknown']
                    correct_eth_value = 0.1  # Default small value
                
                # Use the eth_value as alpha score (which it actually is)
                alpha_score = float(eth_value) if isinstance(eth_value, (int, float)) else 0.0
                
                logger.debug(f"Token {token_name}: wallets={wallet_count}, eth={correct_eth_value}, score={alpha_score}")
                
                # Apply thresholds using the correct ETH value
                if (wallet_count >= thresholds["min_wallets"] and 
                    correct_eth_value >= thresholds["min_eth_total"] and 
                    alpha_score >= thresholds["min_alpha_score"]):
                    
                    # Determine confidence level
                    confidence = determine_confidence(wallet_count, correct_eth_value, alpha_score)
                    
                    alert = {
                        "id": f"{network}_{token_name}_{int(datetime.now().timestamp())}",
                        "timestamp": datetime.now().isoformat(),
                        "token": token_name,
                        "alert_type": "new_token",
                        "confidence": confidence,
                        "network": network,
                        "data": {
                            "total_eth_spent": round(float(correct_eth_value), 4),  # Use correct ETH value
                            "wallet_count": wallet_count,
                            "alpha_score": round(alpha_score, 1),
                            "total_purchases": purchase_count,
                            "platforms": platforms if isinstance(platforms, list) else ['Unknown'],
                            "average_purchase_size": round(float(correct_eth_value) / max(purchase_count, 1), 6),
                            "contract_address": token_info.get('contract_address', '') if isinstance(token_info, dict) else ''
                        }
                    }
                    alerts.append(alert)
                    logger.info(f"✅ Generated buy alert for {token_name}: eth={correct_eth_value:.4f}, score={alpha_score:.1f}")
                
            except Exception as token_error:
                logger.error(f"Error processing individual token {token_name}: {token_error}")
                continue
        
        return alerts
        
    except Exception as e:
        logger.error(f"Error processing buy results: {e}")
        return []
    
def process_sell_results(network: str, results, thresholds: dict) -> List[dict]:
    """Process sell analysis results and generate sell pressure alerts - FIXED ETH VALUES"""
    alerts = []
    
    try:
        if not hasattr(results, 'ranked_tokens') or not results.ranked_tokens:
            logger.info(f"No ranked tokens found in sell results for {network}")
            return alerts
        
        logger.info(f"Processing {len(results.ranked_tokens)} sell tokens for {network}")
        
        for token_data in results.ranked_tokens[:5]:  # Check top 5 for sell pressure
            try:
                token_name, token_info, sell_score = token_data
                
                # Debug log the structure
                logger.debug(f"Processing sell token {token_name}: info type={type(token_info)}, sell_score={sell_score}")
                
                # Handle different token_info structures  
                if isinstance(token_info, dict):
                    wallet_count = len(token_info.get('wallets', set()))
                    sell_count = token_info.get('total_sells', token_info.get('count', 0))
                    
                    # FIXED: Get the correct ETH value from token_info, not the score
                    # The sell_score parameter is actually the sell pressure score, not ETH value!
                    correct_eth_value = token_info.get('total_estimated_eth', 0.0)
                    
                    # Validate and convert the ETH value
                    if isinstance(correct_eth_value, (int, float)):
                        # Check if it's in wei format (very large number)
                        if correct_eth_value > 1000000000000000000:  # More than 1 ETH in wei
                            correct_eth_value = correct_eth_value / 1e18
                            logger.debug(f"🔧 Converted sell ETH from wei: {correct_eth_value}")
                        
                        # Safety cap for unrealistic values
                        if correct_eth_value > 100:  # More than 100 ETH for single sell alert
                            logger.warning(f"⚠️ Capping high sell ETH value for {token_name}: {correct_eth_value} -> 10.0")
                            correct_eth_value = 10.0
                    else:
                        correct_eth_value = 0.0
                        
                else:
                    wallet_count = 1
                    sell_count = 1
                    correct_eth_value = 0.1  # Default small value
                
                # Use the sell_score as the actual sell pressure score
                sell_pressure_score = float(sell_score) if isinstance(sell_score, (int, float)) else 0.0
                
                logger.debug(f"Sell token {token_name}: wallets={wallet_count}, eth={correct_eth_value}, score={sell_pressure_score}")
                
                # Lower threshold for sell pressure alerts (using correct ETH value)
                if (wallet_count >= max(thresholds["min_wallets"] - 1, 1) and 
                    correct_eth_value >= thresholds["min_eth_total"] * 0.5 and 
                    sell_pressure_score >= 20):  # Separate threshold for sell pressure
                    
                    confidence = determine_sell_confidence(wallet_count, correct_eth_value, sell_pressure_score)
                    
                    alert = {
                        "id": f"{network}_{token_name}_sell_{int(datetime.now().timestamp())}",
                        "timestamp": datetime.now().isoformat(),
                        "token": token_name,
                        "alert_type": "sell_pressure",
                        "confidence": confidence,
                        "network": network,
                        "data": {
                            "total_eth_value": round(float(correct_eth_value), 4),  # Use correct ETH value
                            "total_estimated_eth": round(float(correct_eth_value), 4),  # Alias for compatibility
                            "wallet_count": wallet_count,
                            "sell_score": round(sell_pressure_score, 1),
                            "total_sells": sell_count,
                            "methods": ["Token Transfer"],  # Simplified for sell analysis
                            "contract_address": token_info.get('contract_address', '') if isinstance(token_info, dict) else ''
                        }
                    }
                    alerts.append(alert)
                    logger.info(f"✅ Generated sell alert for {token_name}: eth={correct_eth_value:.4f}, score={sell_pressure_score:.1f}")
                
            except Exception as token_error:
                logger.error(f"Error processing individual sell token {token_name}: {token_error}")
                continue
        
        return alerts
        
    except Exception as e:
        logger.error(f"Error processing sell results: {e}")
        return []
    
def calculate_alpha_score(wallet_count: int, purchase_count: int, eth_value: float) -> float:
    """Calculate alpha score for a token based on various factors"""
    try:
        # Ensure we have valid numbers
        wallet_count = max(int(wallet_count), 0)
        purchase_count = max(int(purchase_count), 0)
        eth_value = max(float(eth_value), 0.0)
        
        # ETH value component (0-50 points)
        eth_score = min(eth_value * 10, 50)
        
        # Wallet diversity component (0-30 points)
        wallet_score = min(wallet_count * 5, 30)
        
        # Activity level component (0-20 points)
        activity_score = min(purchase_count * 2, 20)
        
        total_score = eth_score + wallet_score + activity_score
        
        return float(total_score)
        
    except Exception as e:
        logger.error(f"Error calculating alpha score: {e}")
        return 0.0

def calculate_sell_pressure_score(wallet_count: int, sell_count: int, eth_value: float) -> float:
    """Calculate sell pressure score"""
    try:
        # Ensure we have valid numbers
        wallet_count = max(int(wallet_count), 0)
        sell_count = max(int(sell_count), 0)
        eth_value = max(float(eth_value), 0.0)
        
        # ETH value component (0-40 points)
        eth_score = min(eth_value * 8, 40)
        
        # Wallet diversity component (0-25 points)
        wallet_score = min(wallet_count * 4, 25)
        
        # Volume component (0-15 points)
        volume_score = min(sell_count * 1.5, 15)
        
        total_score = eth_score + wallet_score + volume_score
        
        return float(total_score)
        
    except Exception as e:
        logger.error(f"Error calculating sell pressure score: {e}")
        return 0.0

def determine_confidence(wallet_count: int, eth_value: float, alpha_score: float) -> str:
    """Determine confidence level for buy alerts"""
    if wallet_count >= 5 and eth_value >= 2.0 and alpha_score >= 70:
        return "HIGH"
    elif wallet_count >= 3 and eth_value >= 1.0 and alpha_score >= 50:
        return "MEDIUM"
    else:
        return "LOW"

def determine_sell_confidence(wallet_count: int, eth_value: float, sell_score: float) -> str:
    """Determine confidence level for sell pressure alerts"""
    if wallet_count >= 4 and eth_value >= 1.5 and sell_score >= 60:
        return "HIGH"
    elif wallet_count >= 2 and eth_value >= 0.8 and sell_score >= 40:
        return "MEDIUM"
    else:
        return "LOW"

async def send_alert_notifications(alerts: List[dict]):
    """Send notifications for new alerts - ENHANCED VERSION"""
    if not alerts:
        logger.debug("📱 No alerts to send")
        return
    
    logger.info(f"📱 Processing notifications for {len(alerts)} alerts")
    
    # Check if notifications are available
    if not NOTIFICATIONS_AVAILABLE:
        logger.info("📱 Notification services not available - skipping")
        return
    
    # Check configuration
    try:
        from services.notifications import check_notification_config
        if not check_notification_config():
            logger.error("❌ Telegram configuration invalid - skipping notifications")
            return
    except Exception as e:
        logger.error(f"❌ Error checking notification config: {e}")
        return
    
    try:
        # Import here to avoid issues if not available
        from services.notifications import send_alert_notifications as send_notifications
        
        # Send the notifications
        await send_notifications(alerts)
        
        logger.info(f"✅ Notification processing complete for {len(alerts)} alerts")
        
    except Exception as e:
        logger.error(f"❌ Error sending notifications: {e}")
        
def format_alert_message(alert: dict) -> str:
    """Format alert for notifications"""                          
    try:
        data = alert.get('data', {})
        alert_type = alert.get('alert_type', 'unknown')
        confidence = alert.get('confidence', 'LOW')
        
        if alert_type == 'new_token':
            score = data.get('alpha_score', 0)
            message = f"""
🚨 NEW TOKEN ALERT 🚨
Token: {alert['token']}
Network: {alert['network'].upper()}
Confidence: {confidence}
Alpha Score: {score:.1f}
ETH Spent: {data.get('total_eth_spent', 0):.3f}
Wallets: {data.get('wallet_count', 0)}
Purchases: {data.get('total_purchases', 0)}
Platforms: {', '.join(data.get('platforms', []))}
"""
        elif alert_type == 'sell_pressure':
            score = data.get('sell_score', 0)
            message = f"""
📉 SELL PRESSURE ALERT 📉
Token: {alert['token']}
Network: {alert['network'].upper()}
Confidence: {confidence}
Sell Score: {score:.1f}
ETH Value: {data.get('total_eth_value', 0):.3f}
Wallets: {data.get('wallet_count', 0)}
Sells: {data.get('total_sells', 0)}
"""
        else:
            message = f"""
🔔 CRYPTO ALERT 🔔
Token: {alert['token']}
Network: {alert['network'].upper()}
Type: {alert_type.replace('_', ' ').title()}
Confidence: {confidence}
"""
        
        return message.strip()
        
    except Exception as e:
        logger.error(f"Error formatting alert message: {e}")
        return f"🚨 Alert: {alert.get('token', 'Unknown')} on {alert.get('network', 'Unknown')}"