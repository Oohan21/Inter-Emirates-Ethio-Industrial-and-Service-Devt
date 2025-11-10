// frontend/static/js/notifications.js
class NotificationManager {
    constructor() {
        this.unreadCount = 0;
        this.websocket = null;
        this.pollingInterval = null;
        this.useWebSockets = false;
        this.init();
    }
    
    init() {
        this.detectWebSocketSupport();
        this.updateUnreadCount();
        this.setupNotificationBell();
        
        if (this.useWebSockets) {
            this.connectWebSocket();
        } else {
            this.startPolling();
        }
    }
    
    detectWebSocketSupport() {
        this.useWebSockets = window.WebSocket !== undefined;
        console.log(`Using ${this.useWebSockets ? 'WebSockets' : 'AJAX polling'} for notifications`);
    }
    
    connectWebSocket() {
        if (window.WebSocket) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/notifications/`;
            
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                console.log('WebSocket connected for notifications');
            };
            
            this.websocket.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleNotification(data);
            };
            
            this.websocket.onclose = () => {
                console.log('WebSocket disconnected, falling back to polling...');
                this.useWebSockets = false;
                this.startPolling();
            };
        }
    }
    
    startPolling() {
        // Poll for new notifications every 10 seconds
        this.pollingInterval = setInterval(() => {
            this.checkForNewNotifications();
        }, 10000);
        
        // Also check immediately
        this.checkForNewNotifications();
    }
    
    async checkForNewNotifications() {
        try {
            const response = await fetch('/notifications/pending/');
            const data = await response.json();
            
            if (data.success && data.notifications) {
                data.notifications.forEach(notification => {
                    this.handleNotification({
                        type: notification.type,
                        data: notification
                    });
                });
            }
        } catch (error) {
            console.error('Failed to fetch pending notifications:', error);
        }
    }
    
    handleNotification(data) {
        switch (data.type) {
            case 'low_stock':
                this.showPopupNotification(data.data);
                this.updateUnreadCount();
                break;
        }
    }
    
    showPopupNotification(notification) {
        // Create popup element
        const popup = document.createElement('div');
        popup.className = `fixed top-4 right-4 max-w-sm w-full bg-white rounded-lg shadow-lg border-l-4 ${
            notification.priority === 'high' || notification.priority === 'urgent' 
            ? 'border-red-500' 
            : 'border-blue-500'
        } z-50 transform transition-transform duration-300 translate-x-full`;
        
        popup.innerHTML = `
            <div class="p-4">
                <div class="flex justify-between items-start">
                    <div class="flex-1">
                        <h4 class="font-semibold text-gray-800">${notification.title}</h4>
                        <p class="text-sm text-gray-600 mt-1">${notification.message}</p>
                        <div class="flex justify-between items-center mt-3">
                            <span class="text-xs text-gray-500">Just now</span>
                            ${notification.url ? `<a href="${notification.url}" class="text-blue-600 hover:text-blue-800 text-sm font-medium">View</a>` : ''}
                        </div>
                    </div>
                    <button class="close-btn ml-4 text-gray-400 hover:text-gray-600">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(popup);
        
        // Animate in
        setTimeout(() => {
            popup.classList.remove('translate-x-full');
        }, 100);
        
        // Close button
        popup.querySelector('.close-btn').addEventListener('click', () => {
            popup.classList.add('translate-x-full');
            setTimeout(() => {
                document.body.removeChild(popup);
            }, 300);
        });
        
        // Auto-remove after 8 seconds
        setTimeout(() => {
            if (document.body.contains(popup)) {
                popup.classList.add('translate-x-full');
                setTimeout(() => {
                    if (document.body.contains(popup)) {
                        document.body.removeChild(popup);
                    }
                }, 300);
            }
        }, 8000);
    }
    
    async updateUnreadCount() {
        try {
            const response = await fetch('/notifications/unread-count/');
            const data = await response.json();
            this.unreadCount = data.count;
            this.updateNotificationBell();
        } catch (error) {
            console.error('Failed to fetch unread count:', error);
        }
    }
    
    updateNotificationBell() {
        const bell = document.getElementById('notification-bell');
        const badge = document.getElementById('notification-badge');
        
        if (bell && badge) {
            if (this.unreadCount > 0) {
                badge.textContent = this.unreadCount > 99 ? '99+' : this.unreadCount;
                badge.classList.remove('hidden');
                bell.classList.add('animate-pulse');
            } else {
                badge.classList.add('hidden');
                bell.classList.remove('animate-pulse');
            }
        }
    }
    
    setupNotificationBell() {
        const bell = document.getElementById('notification-bell');
        if (bell) {
            bell.addEventListener('click', () => {
                window.location.href = '/notifications/';
            });
        }
    }
    
    async markAsRead(notificationId) {
        try {
            const response = await fetch(`/notifications/${notificationId}/mark-read/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.getCSRFToken(),
                    'Content-Type': 'application/json',
                },
            });
            return await response.json();
        } catch (error) {
            console.error('Failed to mark notification as read:', error);
            return { success: false };
        }
    }
    
    getCSRFToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    
    destroy() {
        if (this.websocket) {
            this.websocket.close();
        }
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
    }
}

// Initialize notification manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.notificationManager = new NotificationManager();
});