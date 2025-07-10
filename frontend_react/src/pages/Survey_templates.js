import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import '../assets/survey_templates.css';

function SurveyTemplates() {
    const [templates, setTemplates] = useState([]);
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState({ text: '', type: '' });
    const [currentTemplateId, setCurrentTemplateId] = useState(null);
    const [questions, setQuestions] = useState([]);
    const [showQuestionsSection, setShowQuestionsSection] = useState(false);
    const [createButtonDisabled, setCreateButtonDisabled] = useState(false);
    const navigate = useNavigate();

    // Form state for adding questions
    const [questionForm, setQuestionForm] = useState({
        question_text: '',
        question_type: 'likert',
        question_category: 'general',
        order: 1,
        answer_choices: {
            1: '',
            2: '',
            3: '',
            4: '',
            5: ''
        }
    });

    const showMessage = (msg, type = 'success') => {
        setMessage({ text: msg, type });
        setTimeout(() => setMessage({ text: '', type: '' }), 2500);
    };

    const fetchTemplates = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/survey-templates/');
            if (response.data.success) {
                setTemplates(response.data.templates);
            } else {
                showMessage(response.data.error || 'Failed to load templates.', 'error');
            }
        } catch (error) {
            showMessage('Error loading templates.', 'error');
        } finally {
            setLoading(false);
        }
    };

    const createTemplate = async () => {
        try {
            setCreateButtonDisabled(true);
            const response = await api.post('/api/survey-templates/', {});
            if (response.data.success) {
                showMessage('Template created!');
                fetchTemplates();
            } else {
                showMessage(response.data.error || 'Failed to create template.', 'error');
            }
        } catch (error) {
            showMessage('Error creating template.', 'error');
        } finally {
            setCreateButtonDisabled(false);
        }
    };

    const applyTemplate = async (templateId) => {
        if (!window.confirm('Are you sure you want to use this template? This will deactivate any currently active template.')) {
            return;
        }
        
        try {
            const response = await api.post(`/api/survey-templates/${templateId}/use/`);
            if (response.data.success) {
                showMessage('Template activated successfully!');
                fetchTemplates();
            } else {
                showMessage(response.data.error || 'Failed to activate template.', 'error');
            }
        } catch (error) {
            showMessage('Error activating template.', 'error');
        }
    };

    const deleteTemplate = async (templateId) => {
        if (!window.confirm('Are you sure you want to delete this template? This will also delete all questions in this template.')) {
            return;
        }
        
        try {
            const response = await api.delete('/api/survey-templates/', {
                data: { template_id: templateId }
            });
            if (response.data.success) {
                showMessage('Template deleted!');
                fetchTemplates();
                
                // If the deleted template was the current one, hide the questions section
                if (currentTemplateId === templateId) {
                    setCurrentTemplateId(null);
                    setShowQuestionsSection(false);
                }
            } else {
                showMessage(response.data.error || 'Failed to delete template.', 'error');
            }
        } catch (error) {
            showMessage('Error deleting template.', 'error');
        }
    };

    const selectTemplate = (templateId) => {
        setCurrentTemplateId(templateId);
        setShowQuestionsSection(true);
        fetchQuestions(templateId);
    };

    const fetchQuestions = async (templateId) => {
        try {
            const response = await api.get(`/api/survey-templates/${templateId}/questions/`);
            if (response.data.success) {
                setQuestions(response.data.questions || []);
            } else {
                showMessage(response.data.error || 'Failed to load questions.', 'error');
            }
        } catch (error) {
            showMessage('Error loading questions.', 'error');
        }
    };

    const addQuestion = async (e) => {
        e.preventDefault();
        if (!currentTemplateId) return;
        
        const payload = {
            question_text: questionForm.question_text,
            question_type: questionForm.question_type,
            question_category: questionForm.question_category,
            order: parseInt(questionForm.order)
        };
        
        // Add answer choices if it's a likert question
        if (questionForm.question_type === 'likert') {
            const answerChoices = {};
            for (let i = 1; i <= 5; i++) {
                const value = questionForm.answer_choices[i];
                if (value) {
                    answerChoices[i] = value;
                }
            }
            
            // Only add if at least one custom choice is defined
            if (Object.keys(answerChoices).length > 0) {
                payload.answer_choices = answerChoices;
            }
        }
        
        try {
            const response = await api.post(`/api/survey-templates/${currentTemplateId}/questions/`, payload);
            if (response.data.success) {
                showMessage('Question added!');
                fetchQuestions(currentTemplateId);
                // Reset form
                setQuestionForm({
                    question_text: '',
                    question_type: 'likert',
                    question_category: 'general',
                    order: 1,
                    answer_choices: { 1: '', 2: '', 3: '', 4: '', 5: '' }
                });
            } else {
                showMessage(response.data.error || 'Failed to add question.', 'error');
            }
        } catch (error) {
            showMessage('Error adding question.', 'error');
        }
    };

    const deleteQuestion = async (questionId) => {
        if (!currentTemplateId) return;
        if (!window.confirm('Are you sure you want to delete this question?')) return;
        
        try {
            const response = await api.delete(`/api/survey-templates/${currentTemplateId}/questions/`, {
                data: { question_id: questionId }
            });
            if (response.data.success) {
                showMessage('Question deleted!');
                fetchQuestions(currentTemplateId);
            } else {
                showMessage(response.data.error || 'Failed to delete question.', 'error');
            }
        } catch (error) {
            showMessage('Error deleting question.', 'error');
        }
    };

    const handleQuestionFormChange = (field, value) => {
        if (field.startsWith('answer_choice_')) {
            const choiceNumber = field.split('_')[2];
            setQuestionForm(prev => ({
                ...prev,
                answer_choices: {
                    ...prev.answer_choices,
                    [choiceNumber]: value
                }
            }));
        } else {
            setQuestionForm(prev => ({ ...prev, [field]: value }));
        }
    };

    const getCategoryOptions = () => {
        if (questionForm.question_type === 'likert') {
            return [
                { value: 'general', label: 'General Question' },
                { value: 'sleep', label: 'Sleep Quality' },
                { value: 'stress', label: 'Stress Level' },
                { value: 'support', label: 'Support Perception' }
            ];
        } else {
            return [{ value: 'general', label: 'General Question' }];
        }
    };

    useEffect(() => {
        fetchTemplates();
    }, []);

    // Reset category when question type changes
    useEffect(() => {
        setQuestionForm(prev => ({ ...prev, question_category: 'general' }));
    }, [questionForm.question_type]);

    return (
        <>
            <Helmet>
                <title>Sowfee Health - Survey Template Management</title>
                <link rel="icon" type="image/x-icon" href="/images/sowfeefavicon.png" />
            </Helmet>
            
            <div className="container">
                <h1>Survey Template Management</h1>
                
                {message.text && (
                    <div id="messages">
                        <div className={`${message.type}-message`}>{message.text}</div>
                    </div>
                )}
                
                <div className="template-list">
                    <h2>Your Survey Templates</h2>
                    <div id="templates">
                        {loading ? (
                            'Loading...'
                        ) : templates.length === 0 ? (
                            <em>No templates found.</em>
                        ) : (
                            templates.map(template => (
                                <div key={template.id} className="template-item">
                                    <div className="template-info">
                                        <strong>Template ID:</strong> {template.id}
                                        {template.used && <span className="badge-success">Currently Used</span>}
                                    </div>
                                    <div className="template-actions">
                                        <button className="btn" onClick={() => selectTemplate(template.id)}>
                                            Edit Questions
                                        </button>
                                        {!template.used && (
                                            <button className="btn btn-primary" onClick={() => applyTemplate(template.id)}>
                                                Use Template
                                            </button>
                                        )}
                                        <button className="btn btn-delete" onClick={() => deleteTemplate(template.id)}>
                                            Delete
                                        </button>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                    <div className="button-row">
                        <button 
                            className="btn" 
                            id="create-template-btn" 
                            onClick={createTemplate}
                            disabled={createButtonDisabled}
                        >
                            Create New Template
                        </button>
                        <div className="home-button-wrapper">
                            <button 
                                className="show-more-btn" 
                                id="home-button"
                                onClick={() => navigate('/')}
                            >
                                Back to Homepage
                            </button>
                        </div>
                    </div>
                </div>
                
                {showQuestionsSection && (
                    <div id="questions-section">
                        <h2>Questions for Template <span id="current-template-id">{currentTemplateId}</span></h2>
                        <div id="questions" className="question-list">
                            {questions.length === 0 ? (
                                <em>No questions for this template.</em>
                            ) : (
                                questions.map(question => (
                                    <div key={question.id} className="question-item">
                                        <strong>Q{question.order}:</strong> {question.question_text} <em>({question.question_type})</em>
                                        <div><small>Category: {question.category}</small></div>
                                        {question.question_type === 'likert' && question.answer_choices && (
                                            <div className="answer-choices-display">
                                                <small>Custom answers: 
                                                    {Object.entries(question.answer_choices).map(([key, value]) => 
                                                        `${key}: ${value} `
                                                    ).join('')}
                                                </small>
                                            </div>
                                        )}
                                        <button className="btn btn-delete" onClick={() => deleteQuestion(question.id)}>
                                            Delete
                                        </button>
                                    </div>
                                ))
                            )}
                        </div>
                        
                        <h3>Add New Question</h3>
                        <form id="add-question-form" onSubmit={addQuestion}>
                            <label>
                                Question Text
                                <input 
                                    type="text" 
                                    value={questionForm.question_text}
                                    onChange={(e) => handleQuestionFormChange('question_text', e.target.value)}
                                    required 
                                />
                            </label>
                            
                            <label>
                                Type
                                <select 
                                    value={questionForm.question_type}
                                    onChange={(e) => handleQuestionFormChange('question_type', e.target.value)}
                                >
                                    <option value="likert">Likert</option>
                                    <option value="text">Text</option>
                                </select>
                            </label>
                            
                            <label>
                                Category
                                <select 
                                    value={questionForm.question_category}
                                    onChange={(e) => handleQuestionFormChange('question_category', e.target.value)}
                                >
                                    {getCategoryOptions().map(option => (
                                        <option key={option.value} value={option.value}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </label>
                            
                            <label>
                                Order
                                <input 
                                    type="number" 
                                    min="1" 
                                    value={questionForm.order}
                                    onChange={(e) => handleQuestionFormChange('order', e.target.value)}
                                    required 
                                />
                            </label>
                            
                            {questionForm.question_type === 'likert' && (
                                <div id="answer-choices-section">
                                    <h4>Custom Answer Choices</h4>
                                    <p className="info-text">Define custom text for each answer choice. Emojis will remain fixed.</p>
                                    <div className="answer-choice-inputs">
                                        {[1, 2, 3, 4, 5].map(num => (
                                            <label key={num}>
                                                {num} ({['😊', '🙂', '😐', '😕', '😞'][num - 1]})
                                                <input 
                                                    type="text" 
                                                    value={questionForm.answer_choices[num]}
                                                    onChange={(e) => handleQuestionFormChange(`answer_choice_${num}`, e.target.value)}
                                                    placeholder={['Excellent', 'Good', 'Neutral', 'Poor', 'Very Poor'][num - 1]}
                                                />
                                            </label>
                                        ))}
                                    </div>
                                </div>
                            )}
                            
                            <button className="btn" type="submit">Add Question</button>
                        </form>
                    </div>
                )}
            </div>
        </>
    );
}

export default SurveyTemplates;