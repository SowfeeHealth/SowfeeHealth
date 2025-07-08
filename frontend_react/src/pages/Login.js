import React, {useState, useEffect} from 'react';
import ReactDOM from 'react-dom/client';
import '../assets/login.css';
import { Helmet } from 'react-helmet';
import api from '../api';
import {getUserStatus} from './Index';
/*
{% if messages %}
      <div id="messageModal" class="modal">
        <div class="modal-content">
          <span class="close-button">&times;</span>
          {% for message in messages %}
          <p
            style="
              {% if message.tags == 'success' %} color: #155724; {% else %} color: #721c24; {% endif %}"
          >
            {{ message }}
          </p>
          {% endfor %}
        </div>
      </div>
      {% endif %}
*/


export function LoginMessage({message, onClose}) {
    return (
        <div id="messageModal" className="modal"  >
            <div className="modal-content">
                <span className="close-button" onClick={onClose}>&times;</span>
                <p style={{
                    color: message.type === 'success' ? '#155724' : '#721c24'
                }}>
                    {message.text}
                </p>
            </div>
        </div>
    );
}

function Head() {
    return (
        <Helmet>
        <meta charSet="UTF-8" />
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-QGYF622KGW"></script>
        <script>
            {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', 'G-QGYF622KGW');
            `}
        </script>
        <title>Sowfee Health - Login</title>
        </Helmet>
      );
}

function Body() {
    const [message, setMessage] = useState(null)
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(true); // Add loading state
    
    // Check if user is already logged in when component loads
    useEffect(() => {
        const checkAuthStatus = async () => {
            try {
                const userData = await getUserStatus();
                
                if (userData && userData.email) {
                    // User is already logged in, redirect based on role
                    if (userData.is_superuser) {
                        // Superuser - redirect to admin or show error
                        setMessage({
                            text: 'Super users cannot access this page',
                            type: 'error'
                        });
                    } else if (userData.is_institution_admin) {
                        // Institution admin - redirect to dashboard
                        window.location.href = '/dashboard/';
                    } else {
                        // Regular user - redirect to survey
                        window.location.href = '/survey/';
                    }
                    return;
                }
            } catch (error) {
                // User not logged in, that's fine for login page
                console.log('User not logged in');
            } finally {
                setLoading(false);
            }
        };
        
        checkAuthStatus();
    }, []);

    const closeMessage = () => {
        setMessage(null);
    };
    
    const handleFormRequest = async () => {
        try {
            const response = await api.post('/api/login/', { email, password });
            
            if (response.data.success) {
                setMessage({
                    text: response.data.message,
                    type: 'success'
                });
                
                // Get user data to determine redirect
                const userData = await getUserStatus();
                
                let redirectPath = '/survey/'; // Default for regular users
                
                if (userData.is_superuser) {
                    setMessage({
                        text: 'Super users cannot access this application',
                        type: 'error'
                    });
                    return;
                } else if (userData.is_institution_admin) {
                    redirectPath = '/dashboard/';
                }
                
                // Redirect after showing success message
                setTimeout(() => {
                    window.location.href = redirectPath;
                }, 600);
            }
            
            return response;
        } catch (error) {
            setMessage({
                text: error.response?.data?.message || 'Login failed',
                type: 'error'
            });
        }
    };
    
    // Show loading while checking auth status
    if (loading) {
        return (
            <div className="login-wrapper">
                <div className="login-container">
                    <div>Checking authentication...</div>
                </div>
            </div>
        );
    }
    const processForm = async (e) => {
        try {
            e.preventDefault();
            await handleFormRequest();
        }
        catch (error) {
            console.error(error);
        }
    }
    return (
        <div className="login-wrapper"> 
            <div className="login-container">
                <div className="login-logo">Sowfee Health</div>

                <form id="loginForm" onSubmit={processForm}>
                    <div className="form-group">
                        <label htmlFor="email">Email</label>
                        <input
                            type="email"
                            id="email"
                            name="email"
                            placeholder="Enter your institutional email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                        />
                    </div>

                    <div className="form-group">
                        <label htmlFor="password">Password</label>
                        <input
                            type="password"
                            id="password"
                            name="password"
                            placeholder="Enter your password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                        />
                    </div>

                    <button type="submit" className="login-btn">Sign In</button>
                </form>

                <div className="register-link-container">
                    <a href="/register/" className="register-link">
                        No Account? Register Now!
                    </a>
                </div>
            </div>
            {message && <LoginMessage message = {message} onClose={closeMessage}/>}
        </div>
    );
}


function Login() {
  return (
    <div>
        <Head />
        <Body />
    </div>
  );
}

export default Login;
