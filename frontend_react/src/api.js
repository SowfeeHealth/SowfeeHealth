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

// Function to ensure CSRF token exists
async function ensureCSRFToken() {
    if (!getCSRFToken()) {
        console.log('No CSRF token found, fetching...');
        await axios.get('http://localhost:8000/api/csrf/', { withCredentials: true });
    }
}

// Configure axios with CSRF token
const api = axios.create({
    baseURL: 'http://localhost:8000',
    // baseURL: 'http://localhost:8000', for development
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