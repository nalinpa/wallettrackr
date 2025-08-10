// PWA functionality and installation
class PWAManager {
  constructor() {
    this.deferredPrompt = null;
    this.isInstalled = false;
    this.isOnline = navigator.onLine;
    
    this.init();
  }
  
  init() {
    this.registerServiceWorker();
    this.setupInstallPrompt();
    this.setupOfflineDetection();
    this.setupPeriodicSync();
    this.createInstallButton();
  }
  
  async registerServiceWorker() {
    if ('serviceWorker' in navigator) {
      try {
        const registration = await navigator.serviceWorker.register('/static/sw.js');
        console.log('[PWA] Service Worker registered:', registration);
        
        // Check for updates
        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              this.showUpdateNotification();
            }
          });
        });
        
      } catch (error) {
        console.log('[PWA] Service Worker registration failed:', error);
      }
    }
  }
  
  setupInstallPrompt() {
    // Listen for beforeinstallprompt event
    window.addEventListener('beforeinstallprompt', (e) => {
      console.log('[PWA] Install prompt available');
      e.preventDefault();
      this.deferredPrompt = e;
      this.showInstallOption();
    });
    
    // Listen for app installed event
    window.addEventListener('appinstalled', () => {
      console.log('[PWA] App installed');
      this.isInstalled = true;
      this.hideInstallOption();
      this.showInstalledMessage();
    });
  }
  
  setupOfflineDetection() {
    window.addEventListener('online', () => {
      this.isOnline = true;
      this.updateConnectionStatus();
      this.syncWhenOnline();
    });
    
    window.addEventListener('offline', () => {
      this.isOnline = false;
      this.updateConnectionStatus();
    });
    
    this.updateConnectionStatus();
  }
  
  setupPeriodicSync() {
    // Setup background sync if supported
    if ('serviceWorker' in navigator && 'sync' in window.ServiceWorkerRegistration.prototype) {
      navigator.serviceWorker.ready.then((registration) => {
        // Register for background sync
        return registration.sync.register('refresh-data');
      }).catch((error) => {
        console.log('[PWA] Background sync not supported');
      });
    }
  }
  
  createInstallButton() {
    // Create install button
    const installBtn = document.createElement('button');
    installBtn.id = 'install-btn';
    installBtn.className = 'btn install-btn';
    installBtn.innerHTML = '📱 Install App';
    installBtn.style.display = 'none';
    installBtn.addEventListener('click', () => this.installApp());
    
    // Add to controls section
    const controls = document.querySelector('.controls');
    if (controls) {
      controls.appendChild(installBtn);
    }
  }
  
  showInstallOption() {
    const installBtn = document.getElementById('install-btn');
    if (installBtn) {
      installBtn.style.display = 'inline-block';
    }
  }
  
  hideInstallOption() {
    const installBtn = document.getElementById('install-btn');
    if (installBtn) {
      installBtn.style.display = 'none';
    }
  }
  
  async installApp() {
    if (this.deferredPrompt) {
      this.deferredPrompt.prompt();
      const { outcome } = await this.deferredPrompt.userChoice;
      
      if (outcome === 'accepted') {
        console.log('[PWA] User accepted install');
      } else {
        console.log('[PWA] User dismissed install');
      }
      
      this.deferredPrompt = null;
    }
  }
  
  updateConnectionStatus() {
    const indicator = document.getElementById('status-indicator');
    if (indicator) {
      if (this.isOnline) {
        indicator.className = 'status-indicator status-online';
        indicator.innerHTML = '🟢 Online';
      } else {
        indicator.className = 'status-indicator status-offline';
        indicator.innerHTML = '🔴 Offline';
      }
    }
  }
  
  syncWhenOnline() {
    if (this.isOnline && 'serviceWorker' in navigator) {
      navigator.serviceWorker.ready.then((registration) => {
        return registration.sync.register('refresh-data');
      });
    }
  }
  
  showUpdateNotification() {
    const notification = document.createElement('div');
    notification.className = 'update-notification';
    notification.innerHTML = `
      <div style="
        position: fixed;
        top: 20px;
        right: 20px;
        background: linear-gradient(135deg, #4caf50, #81c784);
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 10000;
        max-width: 300px;
      ">
        <strong>🔄 Update Available</strong><br>
        <small>Refresh to get the latest features</small><br>
        <button onclick="window.location.reload()" style="
          background: rgba(255,255,255,0.2);
          border: 1px solid rgba(255,255,255,0.3);
          color: white;
          padding: 5px 10px;
          border-radius: 4px;
          margin-top: 8px;
          cursor: pointer;
        ">Refresh Now</button>
      </div>
    `;
    
    document.body.appendChild(notification);
    
    // Auto remove after 10 seconds
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 10000);
  }
  
  showInstalledMessage() {
    const notification = document.createElement('div');
    notification.innerHTML = `
      <div style="
        position: fixed;
        top: 20px;
        right: 20px;
        background: linear-gradient(135deg, #4caf50, #81c784);
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 10000;
      ">
        ✅ App installed successfully!
      </div>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 3000);
  }
}

// Initialize PWA when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  new PWAManager();
});