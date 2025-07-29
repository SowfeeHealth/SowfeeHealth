import axios from 'axios';

// Function to get CSRF token from cookies
function getCSRFToken() {
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

// Determine base URL based on environment
const getBaseURL = () => {
    // Check if we're on localhost (development)
    const isLocalhost = window.location.hostname === 'localhost' || 
                       window.location.hostname === '127.0.0.1' ||
                       window.location.hostname === '0.0.0.0';
    
    if (isLocalhost) {
        // Development mode - point to local backend
        return 'http://localhost:8000';
    } else {
        // Production mode - use relative URLs (served from same domain)
        return '';
    }
};

// Function to ensure CSRF token exists
async function ensureCSRFToken() {
    if (!getCSRFToken()) {
        console.log('No CSRF token found, fetching...');
        const baseURL = getBaseURL();
        const csrfURL = baseURL ? `${baseURL}/api/csrf/` : '/api/csrf/';
        await axios.get(csrfURL, { withCredentials: true });
    }
}

// Configure axios with dynamic base URL
const api = axios.create({
    baseURL: getBaseURL(),
    withCredentials: true,
});

// Add request interceptor to include CSRF token in every request
api.interceptors.request.use(
    async (config) => {
        try {
            await ensureCSRFToken();
        } catch (error) {
            console.error('Failed to get CSRF token:', error);
        }
        const token = getCSRFToken();
        if (token) {
            config.headers['X-CSRFToken'] = token;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

export default api;