import {Helmet} from 'react-helmet';
import '../assets/survey.css';
import react, {useState, useEffect} from 'react';
import api from '../api';
import {getUserStatus} from './Index';
import { LoginMessage } from './Login';

export const fetchSurveyQuestions = async () => {
  try {
      const response = await api.get('/api/get-user-survey-questions/');
      return response.data;  // this will contain all User fields since fields = "__all__"
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
        <meta name="viewport" content="width=device-width, initial-scale=1.0"></meta>
        <title>Sowfee Health - Student Wellness Survey</title>
        <link
        rel="stylesheet"
        href= "{% static 'survey.css' %}"
        />
    </Helmet>
    );
}

function SurveyQuestions() {
    const [studentName, setStudentName] = useState('');
    const [studentEmail, setStudentEmail] = useState('');
    const [templateId, setTemplateId] = useState(0);
    const [loading, setLoading] = useState(true);
    const [surveyQuestions, setSurveyQuestions] = useState([]);
    const [questionAnswers, setQuestionAnswers] = useState({});
    const [hasQuestions, setHasQuestions] = useState(true); // Add this state
    const [message, setMessage] = useState(null);
    const [isAdmin, setIsAdmin] = useState(false);

    const closeMessage = () => {
        setMessage(null);
    };
    
    const fetchData = async () => {
        try {
            const responseData = await fetchSurveyQuestions();
            const userData = await getUserStatus();
            // Check if user is authenticated
            if (!userData || !userData.email) {
                // Redirect to login
                window.location.href = '/api/login/';
                return;
            }

            setStudentEmail(userData.email);
            setStudentName(userData.name);
            setIsAdmin(userData.is_institution_admin || false);  // Add this line
            setTemplateId(responseData.template_id);
            
            // Check if questions array is empty
            if (!responseData.questions || responseData.questions.length === 0) {
                setHasQuestions(false); // Set to false instead of throwing error
                setSurveyQuestions([]);
            } else {
                setSurveyQuestions(responseData.questions);
                setHasQuestions(true);
            }
            
        } catch (error) {
            console.error('Error fetching data:', error);
            setHasQuestions(false); // Also set to false on error
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);
    
    if (loading) return <div>Loading...</div>;

    const handleAnswerChange = (questionId, value) => {
    setQuestionAnswers({
        ...questionAnswers,
        [questionId]: value  // Use just the question ID
    });
};
    
    const handleSurveyRequest = async () => {
    try {
        const response = await api.post('/api/survey/', { 
            student_name: studentName,
            school_email: studentEmail,
            survey_template_id: templateId,
            ...questionAnswers
        });
        if (response.data.success) {
            setMessage({
                text: response.data.message,
                type: 'success'
            });
        }
        setTimeout(()=> {
            window.location.href = '/';
        }, 600);
        return response;
    }
    catch (error) {
        setMessage({
            text: error.response?.data?.message || 'Survey submission failed',
            type: 'error'
        });
        }
    }

    const processSurvey = async (e) => {
        if (Object.keys(questionAnswers).length !== surveyQuestions.length) {
        setMessage({
            text: 'Please fill in all required fields',
            type: 'error'
        });
        return;
    }
        try {
            e.preventDefault();
            await handleSurveyRequest();
        }
        catch (error) {
            console.error(error);
        }
    }

    const renderQuestion = (question) => {
        if (question.type === 'likert') {
            // Define default Likert options
            const defaultOptions = [
                { value: '5', emoji: '😞', text: 'Very Poor' },
                { value: '4', emoji: '😕', text: 'Poor' },
                { value: '3', emoji: '😐', text: 'Neutral' },
                { value: '2', emoji: '🙂', text: 'Good' },
                { value: '1', emoji: '😊', text: 'Excellent' }
            ];
            
            // Use custom answer choices if available
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
                            return (<label key={option.value} className={`likert-option ${isChecked ? 'selected' : ''}`}>
                                <div>{option.emoji}</div>
                                <input
                                    type="radio"
                                    name={`question_${question.id}`}
                                    value={option.value}
                                    style={{margin: '5px'}}
                                    checked={isChecked}
                                    onChange = {()=>handleAnswerChange(question.id, option.value)}
                                />
                                <div style={{fontSize: '12px'}}>{option.text}</div>
                            </label>
                        )})}
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
                <div className="survey-header">
                    <h1>Student Wellness Check</h1>
                    <p>Your feedback helps us improve student support services</p>
                    <div className="survey-progress">
                        <div className="survey-progress-bar"></div>
                    </div>
                </div>
            </div>
            <form id="wellnessSurvey" onSubmit={processSurvey}>
                {/*Survey form*/}
                <div className="student-info">
                    <div className="info-field">
                        <label>Full Name</label>
                        <input type="text" name="student_name" value={studentName} readOnly 
                            title="Your full name (pre-filled)" />
                    </div>
                    
                    <div className="info-field">
                        <label>School Email</label>
                        <input type="email" name="school_email" value={studentEmail} readOnly
                            title="Your .edu email address (pre-filled)" />
                    </div>
                    
                    { /*Hidden field for survey template ID */}
                    <input type="hidden" name="survey_template_id" id="survey_template_id" />
                </div>

                {/* Dynamic Survey Questions will be loaded here */}
                <div id="dynamic-questions">
                    {loading && <div className="loading">Loading survey questions...</div>}
                    {hasQuestions && surveyQuestions.map(question => renderQuestion(question))}
                    
                    {!hasQuestions && (
                        <div className="no-questions-message">
                            <p>No survey questions are currently available for your institution. Please contact your administrator.</p>
                        </div>
                    )}
                </div>
                
                {/* Conditional rendering for submit button */}
                    {hasQuestions ? (
                        isAdmin ? (
                            <div className="submit-btn disabled-submit">
                                Preview Mode - Admins cannot submit surveys
                            </div>
                        ) : (
                            <button type="submit" className="submit-btn">Submit Wellness Check</button>
                        )
                    ) : (
                        <div className="submit-btn disabled-submit">
                            Survey not available - Your institution doesn't have a survey template
                        </div>
                    )}
                
                <p className="privacy-note">
                    Your responses are confidential and protected by FERPA regulations.<br />
                    Data will only be used to improve student support services.
                </p>
            </form>
        {message && <LoginMessage message={message} onClose={closeMessage}/>}
        </div>
    )
}

function Survey() {
    return (
        <div>
            <Head />
            <SurveyQuestions />
        </div>
    )
}
export default Survey;