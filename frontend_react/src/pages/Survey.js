import {Helmet} from 'react-helmet';
import react, {useState, useEffect} from 'react';
import { useParams } from 'react-router-dom';
import api from '../api';
import {getUserStatus} from './Index';
import { LoginMessage } from './Login';

export const fetchSurveyQuestions = async (hashLink = null) => {
  try {
      let url = '/api/get-user-survey-questions/';
      if (hashLink) {
          // Use your hash link endpoint
          url = `/api/get-user-survey-questions/${hashLink}/`;
      }
      const response = await api.get(url);
      return response.data;
  } catch (error) {
      if (error.response?.status === 401) {
          return { isAuthenticated: false };
      }
      throw error;
  }
};

function Head() {
    return (
    <Helmet>
        <title>Sowfee Health - Student Wellness Survey</title>
    </Helmet>
    );
}

function SurveyQuestions() {
    const { hashLink } = useParams(); // Get hash link from URL parameters
    const [studentName, setStudentName] = useState('');
    const [studentEmail, setStudentEmail] = useState('');
    const [templateId, setTemplateId] = useState(0);
    const [loading, setLoading] = useState(true);
    const [surveyQuestions, setSurveyQuestions] = useState([]);
    const [questionAnswers, setQuestionAnswers] = useState({});
    const [hasQuestions, setHasQuestions] = useState(true);
    const [message, setMessage] = useState(null);
    const [isAdmin, setIsAdmin] = useState(false);
    const [isHashLinkSurvey, setIsHashLinkSurvey] = useState(false);
    const [isAuthenticated, setIsAuthenticated] = useState(false);

    const closeMessage = () => {
        setMessage(null);
    };
    
    const fetchData = async () => {
        try {
            // Determine if this is a hash link survey
            const hashLinkProvided = !!hashLink;
            setIsHashLinkSurvey(hashLinkProvided);
            
            if (hashLinkProvided) {
                // For hash link surveys, fetch questions directly
                const responseData = await fetchSurveyQuestions(hashLink);
                
                if (responseData.success && responseData.questions && responseData.questions.length > 0) {
                    setSurveyQuestions(responseData.questions);
                    setTemplateId(responseData.template_id);
                    setHasQuestions(true);
                    
                    // Try to get user data if authenticated, but don't require it
                    try {
                        const userData = await getUserStatus();
                        if (userData && userData.email) {
                            setStudentEmail(userData.email);
                            setStudentName(userData.name);
                            setIsAdmin(userData.is_institution_admin || false);
                            setIsAuthenticated(true);
                        }
                    } catch (error) {
                        // User not authenticated - that's okay for hash link surveys
                    }
                } else {
                    setHasQuestions(false);
                    setSurveyQuestions([]);
                }
                // In your fetchData function in Survey.js, after setting up the questions:
                const savedAnswers = sessionStorage.getItem('pendingSurvey');
                if (savedAnswers && hashLinkProvided) {
                    try {
                        const parsed = JSON.parse(savedAnswers);
                        setQuestionAnswers(parsed);
                        sessionStorage.removeItem('pendingSurvey'); // Clean up
                    } catch (e) {
                        console.error('Error restoring survey answers:', e);
                    }
                }
            } else {
                // Regular survey flow - requires authentication
                const userData = await getUserStatus();
                if (!userData || !userData.email) {
                    window.location.href = '/login/';
                    return;
                }

                setStudentEmail(userData.email);
                setStudentName(userData.name);
                setIsAdmin(userData.is_institution_admin || false);
                setIsAuthenticated(true);
                
                const responseData = await fetchSurveyQuestions();
                if (responseData.success) {
                    setTemplateId(responseData.template_id);
                    
                    if (!responseData.questions || responseData.questions.length === 0) {
                        setHasQuestions(false);
                        setSurveyQuestions([]);
                    } else {
                        setSurveyQuestions(responseData.questions);
                        setHasQuestions(true);
                    }
                } else {
                    setHasQuestions(false);
                    setSurveyQuestions([]);
                }
            }
            
        } catch (error) {
            console.error('Error fetching data:', error);
            setHasQuestions(false);
            if (error.response?.status === 404 && hashLink) {
                setMessage({
                    text: 'Survey link not found or has expired.',
                    type: 'error'
                });
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [hashLink]); // Re-fetch when hashLink changes
    
    const [isSubmitted, setIsSubmitted] = useState(false);

    useEffect(() => {
    const autoSave = async () => {
        // For authenticated users - save to backend
        if (isAuthenticated) {
            try {
                const response = await api.post('/api/autosave/', {
                    template_id: templateId,
                    student_name: studentName,
                    school_email: studentEmail,
                    answers: questionAnswers,
                });
            } catch (error) {
                console.error("Error saving survey");
            }
        } else {
            // For anonymous users - save to sessionStorage
            const autosaveData = {
                templateId,
                answers: questionAnswers,
                studentName,
                studentEmail,
                lastSaved: new Date().toISOString()
            };
            sessionStorage.setItem(`survey_autosave_${templateId}`, JSON.stringify(autosaveData));
        }
    };
    const interval = setInterval(() => {
            if (isSubmitted) return;
            if (Object.keys(questionAnswers).length === 0) return;
            autoSave();
    }, 3000);
    
    return () => clearInterval(interval);
}, [questionAnswers, studentEmail, studentName, templateId, isAuthenticated]);

    useEffect(() => {
    const autoSaveLoad = async () => {
        if (!templateId) return;
        
        if (isAuthenticated) {
            // Load from backend
            try {
                const response = await api.get(`/api/autosave/load/${templateId}`);
                if (response.data.success) {
                    setQuestionAnswers(response.data.saved_data.answers);
                }
            } catch (error) {
                console.error("Error loading survey");
            }
        } else {
            // Load from sessionStorage for anonymous users
            const saved = sessionStorage.getItem(`survey_autosave_${templateId}`);
            if (saved) {
                const data = JSON.parse(saved);
                setQuestionAnswers(data.answers);
                if (data.studentName) setStudentName(data.studentName);
                if (data.studentEmail) setStudentEmail(data.studentEmail);
            }
        }
    };
    
    autoSaveLoad();
}, [templateId, isAuthenticated]);
    
    if (loading) return <div>Loading...</div>;

    const handleAnswerChange = (questionId, value) => {
        setQuestionAnswers({
            ...questionAnswers,
            [questionId]: value
        });
    };
    
    const clearAutosave = async () => {
        if (!templateId) return;
        
        try {
            await api.delete(`/api/autosave/clear/${templateId}/`);
            
            // Verify the autosave was actually cleared
            const verifyResponse = await api.get(`/api/autosave/load/${templateId}`);
            if (verifyResponse.data.success && verifyResponse.data.saved_data) {
                console.warn('Autosave not fully cleared, retrying...');
                // Retry once more
                await api.delete(`/api/autosave/clear/${templateId}/`);
            }
            
            console.log('Autosave cleared successfully');
        } catch (error) {
            console.error('Error clearing autosave:', error);
            throw error; // Re-throw to handle in calling function
        }
    };

    const handleSurveyRequest = async () => {
        try {
            let url = '/api/survey/';
            let requestData = {
                survey_template_id: templateId,
                ...questionAnswers
            };
    
            // For hash link surveys, use the hash link endpoint
            if (isHashLinkSurvey) {
                url = `/api/survey/link/${hashLink}/`;
                // Include student info if available
                if (studentName) requestData.student_name = studentName;
                if (studentEmail) requestData.school_email = studentEmail;
            } else {
                // For regular surveys, include required student info
                requestData.student_name = studentName;
                requestData.school_email = studentEmail;
            }
    
            const response = await api.post(url, requestData);
            
            // Check for requires_auth in successful response
            if (response.data.requires_auth) {
                // Store the survey data in sessionStorage to preserve it
                sessionStorage.setItem('pendingSurvey', JSON.stringify(questionAnswers));
                // Redirect to login with the current page as the 'next' parameter
                const currentUrl = window.location.pathname;
                window.location.href = `/login/?next=${encodeURIComponent(currentUrl)}`;
                return;
            }
            
            if (response.data.success) {
                await clearAutosave();  
                setMessage({
                    text: response.data.message,
                    type: 'success'
                });
                setIsSubmitted(true);
                setTimeout(() => {
                window.location.href = '/';
            }, 3000);
            } else {
                setMessage({
                    text: response.data.message,
                    type: 'error'
                });
            }
            
            return response;
        } catch (error) {
            if (error.response?.data?.requires_auth) {
                // Store the survey data in sessionStorage to preserve it
                sessionStorage.setItem('pendingSurvey', JSON.stringify(questionAnswers));
                // Redirect to login with the current page as the 'next' parameter
                const currentUrl = window.location.pathname;
                window.location.href = `/login/?next=${encodeURIComponent(currentUrl)}`;
            } else {
                setMessage({
                    text: error.response?.data?.message || 'Survey submission failed',
                    type: 'error'
                });
            }
        }
    };

    const processSurvey = async (e) => {
        e.preventDefault();
        
        if (Object.keys(questionAnswers).length !== surveyQuestions.length) {
            setMessage({
                text: 'Please fill in all required fields',
                type: 'error'
            });
            return;
        }
        
        try {
            await handleSurveyRequest();
        } catch (error) {
            console.error(error);
        }
    };

    const renderQuestion = (question) => {
        if (question.type === 'likert') {
            const defaultOptions = [
                { value: '5', emoji: '😞', text: 'Very Poor' },
                { value: '4', emoji: '😕', text: 'Poor' },
                { value: '3', emoji: '😐', text: 'Neutral' },
                { value: '2', emoji: '🙂', text: 'Good' },
                { value: '1', emoji: '😊', text: 'Excellent' }
            ];
            
            const options = defaultOptions.map(option => {
                if (question.answer_choices && question.answer_choices[option.value]) {
                    return {
                        ...option,
                        text: question.answer_choices[option.value]
                    }
                }
                return option;
            });
            
            return (
                <div className='question-group' key={question.id}>
                    <label>{question.text}</label>
                    <div className='likert-scale'>
                        {options.map((option) => {
                            const isChecked = String(questionAnswers[question.id]) === String(option.value);
                            return (
                                <label key={option.value} className={`likert-option ${isChecked ? 'selected' : ''}`}>
                                    <div>{option.emoji}</div>
                                    <input
                                        type="radio"
                                        name={`question_${question.id}`}
                                        value={option.value}
                                        style={{margin: '5px'}}
                                        checked={isChecked}
                                        onChange={() => handleAnswerChange(question.id, option.value)}
                                    />
                                    <div style={{fontSize: '12px'}}>{option.text}</div>
                                </label>
                            );
                        })}
                    </div>
                </div>
            );
        }
        
        if (question.type === 'text') {
            return (
                <div className='question-group' key={question.id}>
                    <label>{question.text}</label>
                    <div className='text-input-container'>
                        <textarea
                            className='text-response'
                            placeholder="Enter your answer here..."
                            rows="4"
                            value={questionAnswers[question.id] || ''}
                            onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                        />
                    </div>
                </div>
            );
        }
        
        return null;
    };

    return (
        <div className='survey-container'>
            <div className="survey-container">
                <button 
                    type="button"
                    className="back-button"
                    onClick={() => window.location.href = '/'}
                >
                    ← Back
                </button>
                {Object.keys(questionAnswers).length > 0 && (
                    <div className="start-fresh-container">
                        <button 
                            type="button"
                            className="start-fresh-btn"
                            onClick={async () => {
                                if (window.confirm('Are you sure you want to start over? This will clear all your answers.')) {
                                    if (isAuthenticated) {
                                        await clearAutosave();
                                    } else {
                                        // Clear sessionStorage for anonymous users
                                        sessionStorage.removeItem(`survey_autosave_${templateId}`);
                                    }
                                    setQuestionAnswers({});
                                }
                            }}
                            aria-label="Start fresh"
                        >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
                                <path d="M3 3v5h5" />
                            </svg>
                            <span className="mobile-text">Start fresh</span>
                        </button>
                    </div>
                )}
                <div className="survey-header">
                    <h1>Student Wellness Check</h1>
                    <p>Your feedback helps us improve student support services</p>
                    {isHashLinkSurvey && (
                        <p style={{color: '#666', fontSize: '14px'}}>
                            Survey accessed via shared link
                        </p>
                    )}
                    <div className="survey-progress">
                        <div className="survey-progress-bar"></div>
                    </div>
                </div>
            </div>
            
            <form id="wellnessSurvey" onSubmit={processSurvey}>
                {/* Student info section */}
                <div className="student-info">
                    <div className="info-field">
                        <label>Full Name</label>
                        <input 
                            type="text" 
                            name="student_name" 
                            value={studentName} 
                            readOnly={!isHashLinkSurvey || (isHashLinkSurvey && isAuthenticated)}
                            onChange={(e) => setStudentName(e.target.value)}
                            placeholder={isHashLinkSurvey && !studentName ? "Enter your full name" : ""}
                            title={isHashLinkSurvey ? "Your full name" : "Your full name (pre-filled)"} 
                        />
                    </div>
                    
                    <div className="info-field">
                        <label>School Email</label>
                        <input 
                            type="email" 
                            name="school_email" 
                            value={studentEmail} 
                            readOnly={!isHashLinkSurvey || (isHashLinkSurvey && isAuthenticated)}
                            onChange={(e) => setStudentEmail(e.target.value)}
                            placeholder={isHashLinkSurvey && !isAuthenticated ? "Enter your school email" : ""}
                            title={isHashLinkSurvey ? "Your school email address" : "Your .edu email address (pre-filled)"} 
                        />
                    </div>
                    
                    <input type="hidden" name="survey_template_id" id="survey_template_id" />
                </div>

                {/* Dynamic Survey Questions */}
                <div id="dynamic-questions">
                    {loading && <div className="loading">Loading survey questions...</div>}
                    {hasQuestions && surveyQuestions.map(question => renderQuestion(question))}
                    
                    {!hasQuestions && (
                        <div className="no-questions-message">
                            <p>
                                {isHashLinkSurvey 
                                    ? "This survey is not available or may have expired."
                                    : "No survey questions are currently available for your institution. Please contact your administrator."
                                }
                            </p>
                        </div>
                    )}
                </div>
                
                {/* Submit button logic */}
                {hasQuestions ? (
                    isAdmin ? (
                        <div className="submit-btn disabled-submit">
                            Admins cannot submit surveys
                        </div>
                    ) : (
                        <button type="submit" className="submit-btn">
                            Submit Wellness Check
                        </button>
                    )
                ) : (
                    <div className="submit-btn disabled-submit">
                        Survey not available
                    </div>
                )}
                
                <p className="privacy-note">
                    Your responses are confidential and protected by FERPA regulations.<br />
                    Data will only be used to improve student support services.
                </p>
            </form>
            
            {message && <LoginMessage message={message} onClose={closeMessage}/>}
        </div>
    );
}

function Survey() {
    return (
        <div>
            <Head />
            <SurveyQuestions />
        </div>
    );
}

export default Survey;