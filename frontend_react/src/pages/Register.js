import React, {useState, useEffect} from 'react';
import ReactDOM from 'react-dom/client';
import '../assets/register.css';
import { Helmet } from 'react-helmet';
import api from '../api';
import { LoginMessage } from './Login';

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
        <title>Sowfee Health - Register</title>
        </Helmet>
      );
}

function Body() {
    const [message, setMessage] = useState(null);
    const [institutions, setInstitutions] = useState([]);
    const [isSecondPage, setIsSecondPage] = useState(false);
    const [formData, setFormData] = useState({
    institution_name: '',
    name: '',
    email: '',
    password: '',
    confirm_password: ''});

    const closeMessage = () => {
        setMessage(null);
    };

    const nextPage = () => {
        if (formData.institution_name && formData.name.trim()) {
            setIsSecondPage(true);
        } else {
            // Show error or prevent navigation
            setMessage({
            text: 'Please select an institution and enter your full name',
            type: 'error'
        });
        }
    }
    const previousPage = () => {
        setIsSecondPage(false);
    }

    const handleInputChange = (e) => {
    setFormData({
        ...formData,
        [e.target.name]: e.target.value
    });
    };
    
    const handleFormRequest = async () => {
    try {
        const response = await api.post('/api/register/', { institution_name: formData.institution_name, name: formData.name, email: formData.email, password: formData.password, confirm_password: formData.confirm_password});
        if (response.data.success) {
            setMessage({
                text: response.data.message,
                type: 'success'
            });
        }
        setTimeout(()=> {
            window.location.href = '/login/';
        }, 600);
        return response;
    }
    catch (error) {
        setMessage({
            text: error.response?.data?.message || 'Registration failed',
            type: 'error'
        });
        }
    }

    const processForm = async (e) => {
        if (!formData.institution_name || !formData.name || !formData.email || !formData.password || !formData.confirm_password) {
        setMessage({
            text: 'Please fill in all required fields',
            type: 'error'
        });
        return;
    }
        try {
            e.preventDefault();
            await handleFormRequest();
        }
        catch (error) {
            console.error(error);
        }
    }

    useEffect(() => {
    // Fetch institutions on component mount
    api.get('/api/institutions/')
        .then(response => {
            setInstitutions(response.data);
        })
        .catch(error => console.error('Failed to load institutions:', error));
    }, []);

    return(
    <div className="login-wrapper">  
        <div className="login-container">
        <div className="login-logo">Sowfee Health</div>

        <form id="loginForm" onSubmit={processForm}>
            
            {!isSecondPage && (<div id="one">
                
            <div className="form-group select-container">
                <label htmlFor="institution_name">Institution <span className="required-symbol">*</span></label>
                    <select
                        className="form-select"
                        name="institution_name"
                        id="institution_name"
                        defaultValue=""
                        value={formData.institution_name}
                        onChange={handleInputChange}
                        required
                    >
                    <option value="" disabled> Select your institution </option>
                        {institutions.map((institution) => (
                        <option key={institution.id} value={institution.institution_name}> 
                            {institution.institution_name} 
                        </option>
                        ))}
                    </select>
                    <span id="institution-error" className="error_message"></span>
            </div>
            
            <div className="form-group">
                <label htmlFor="name">Full Name <span className="required-symbol">*</span></label>
                <input
                type="text"
                id="name"
                name="name"
                placeholder="Enter your full name"
                value={formData.name}
                onChange={handleInputChange}
                required
                />
                <span id="name-error" className="error_message"></span>
            </div>
            </div>)}
            
            {isSecondPage && (<div id="two">
            <div className="form-group">
                <label htmlFor="email">Email <span className="required-symbol">*</span></label>
                <input
                type="email"
                id="email"
                name="email"
                placeholder="Enter your institutional email"
                value={formData.email}
                onChange={handleInputChange}
                required
                />
                <span id="email-error" className="error_message"></span>
            </div>

            <div className="form-group">
                <label htmlFor="password">Password <span className="required-symbol">*</span></label>
                <input
                type="password"
                id="password"
                name="password"
                placeholder="Enter your password"
                value={formData.password}
                onChange={handleInputChange}
                required
                />
                <span id="password-error" className="error_message"></span>
            </div>

            <div className="form-group">
                <label htmlFor="confirm_password">Confirm Password <span className="required-symbol">*</span></label>
                <input
                type="password"
                id="confirm_password"
                name="confirm_password"
                placeholder="Confirm your password"
                value={formData.confirm_password}
                onChange={handleInputChange}
                required
                />
                <span id="confirm-password-error" className="error_message"></span>
            </div>
            </div>)}

            <div className="step-indicator">
                <span className={`step ${!isSecondPage ? 'active' : 'completed'}`}></span>
                <span className={`step ${isSecondPage ? 'active' : ''}`}></span>
            </div>

            <div className="button-container">
                <div className="button-group">
                    {isSecondPage && (
                        <button type="button" className="login-btn" id="prevBtn" onClick={previousPage}>
                            Previous
                        </button>
                    )}
                    
                    {!isSecondPage && (
                        <button type="button" className="login-btn" id="nextBtn" onClick={nextPage}>
                            Next
                        </button>
                    )}
                    
                    {isSecondPage && (
                        <button type="submit" className="login-btn submit-button" id="submit_btn">
                            Submit
                        </button>
                    )}
                </div>
            </div>
        </form>
        {message && <LoginMessage message = {message} onClose={closeMessage}/>}
        </div>
    </div>
    );
}

function Register() {
  return (
    <div>
        <Head />
        <Body />
    </div>
  );
}

export default Register;