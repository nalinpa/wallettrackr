
// Minimal JavaScript for FastAPI app
function showToast(message, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${message}`);
    alert(message); // Fallback for now
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard!', 'success');
    }).catch(() => {
        showToast('Failed to copy', 'error');
    });
}

function refreshData() {
    location.reload();
}

function exportData() {
    showToast('Export feature coming soon!', 'info');
}

function showSettings() {
    showToast('Settings coming soon!', 'info');
}
