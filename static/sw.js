
// Minimal service worker
const CACHE_NAME = 'crypto-alpha-v1';

self.addEventListener('install', function(event) {
    console.log('Service Worker installing');
});

self.addEventListener('fetch', function(event) {
    // Let the browser handle requests normally
});
