import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import '../assets/schedule-survey.css';

function ScheduleSurvey() {
    const [formData, setFormData] = useState({
        surveyDay: '',
        hour: '',
        minute: '',
        ampm: 'AM',
        recurringSurvey: false,
        emailGroup: ''
    });
    const [isConnected, setIsConnected] = useState(false);
    const [emailGroups, setEmailGroups] = useState([]);
    const [showGroupSelection, setShowGroupSelection] = useState(false);
    const navigate = useNavigate();

    const handleInputChange = (e) => {
        const { name, value, type, checked } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? checked : value
        }));
    };

    const limitInput = (input, maxLength) => {
        if (input.value.length > maxLength) {
            input.value = input.value.slice(0, maxLength);
        }
    };

    const handleConnectGmail = () => {
        // Simulate Gmail connection
        console.log('Connecting to Gmail...');
        setIsConnected(true);
        // Simulate fetching email groups
        const mockGroups = [
            { id: 'students', name: 'Students' },
            { id: 'faculty', name: 'Faculty' },
            { id: 'staff', name: 'Staff' },
            { id: 'all', name: 'All Users' }
        ];
        setEmailGroups(mockGroups);
        setShowGroupSelection(true);
    };

    const handleConnectOutlook = () => {
        // Simulate Outlook connection
        console.log('Connecting to Outlook...');
        setIsConnected(true);
        // Simulate fetching email groups
        const mockGroups = [
            { id: 'department1', name: 'Department 1' },
            { id: 'department2', name: 'Department 2' },
            { id: 'administrators', name: 'Administrators' }
        ];
        setEmailGroups(mockGroups);
        setShowGroupSelection(true);
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        console.log('Survey scheduled:', formData);
        alert('Survey scheduled successfully!');
    };

    return (
        <>
            <Helmet>
                <title>Schedule Survey - Sowfee Health</title>
                <link rel="icon" type="image/x-icon" href="/images/sowfeefavicon.png" />
            </Helmet>
            
            <div className="schedule-container">
                {/* Header */}
                <header className="header">
                    <div className="header-content">
                        <h1 className="header-title">Schedule Survey</h1>
                    </div>
                </header>

                <div className="main-layout">
                    {/* Sidebar */}
                    <nav className="sidebar">
                        <ul>
                            <li>
                                <button 
                                    onClick={() => navigate('/dashboard')} 
                                    className="nav-link"
                                >
                                    Analytics
                                </button>
                            </li>
                            <li>
                                <button 
                                    onClick={() => navigate('/')} 
                                    className="nav-link active"
                                >
                                    Back to Homepage
                                </button>
                            </li>
                        </ul>
                    </nav>

                    <main className="main-content">
                        {/* Survey Scheduling Form */}
                        <div className="form-container">
                            <h2 className="form-title">Schedule a Survey</h2>
                            <form onSubmit={handleSubmit}>
                                
                                {/* Choose Day */}
                                <div className="form-group">
                                    <label htmlFor="surveyDay" className="form-label">Choose the Day</label>
                                    <select 
                                        id="surveyDay" 
                                        name="surveyDay" 
                                        value={formData.surveyDay}
                                        onChange={handleInputChange}
                                        className="form-select" 
                                        required
                                    >
                                        <option value="">Select a Day</option>
                                        <option value="monday">Monday</option>
                                        <option value="tuesday">Tuesday</option>
                                        <option value="wednesday">Wednesday</option>
                                        <option value="thursday">Thursday</option>
                                        <option value="friday">Friday</option>
                                        <option value="saturday">Saturday</option>
                                        <option value="sunday">Sunday</option>
                                    </select>
                                </div>

                                {/* Choose Time */}
                                <div className="form-group">
                                    <label className="form-label">Choose the Time</label>
                                    <div className="time-input-group">
                                        <input 
                                            type="number" 
                                            name="hour" 
                                            min="1" 
                                            max="12" 
                                            value={formData.hour}
                                            onChange={handleInputChange}
                                            onInput={(e) => limitInput(e.target, 2)}
                                            className="time-input" 
                                            required 
                                            placeholder="Hour" 
                                        />
                                        <span className="time-separator">:</span>
                                        <input 
                                            type="number" 
                                            name="minute" 
                                            min="0" 
                                            max="59" 
                                            value={formData.minute}
                                            onChange={handleInputChange}
                                            onInput={(e) => limitInput(e.target, 2)}
                                            className="time-input" 
                                            required 
                                            placeholder="Minutes" 
                                        />
                                        <select 
                                            name="ampm" 
                                            value={formData.ampm}
                                            onChange={handleInputChange}
                                            className="ampm-select"
                                        >
                                            <option value="AM">AM</option>
                                            <option value="PM">PM</option>
                                        </select>
                                    </div>
                                </div>

                                {/* Recurring Survey Checkbox */}
                                <div className="checkbox-group">
                                    <input 
                                        type="checkbox" 
                                        id="recurringSurvey" 
                                        name="recurringSurvey" 
                                        checked={formData.recurringSurvey}
                                        onChange={handleInputChange}
                                        className="checkbox" 
                                    />
                                    <label htmlFor="recurringSurvey" className="checkbox-label">
                                        Make this a recurring survey
                                    </label>
                                </div>

                                {/* Email Connection Selection */}
                                <div className="form-group">
                                    <label className="form-label">Connect to an Email Service</label>
                                    <div className="button-group">
                                        <button 
                                            type="button" 
                                            onClick={handleConnectGmail}
                                            className="connect-btn gmail-btn"
                                        >
                                            Connect to Gmail
                                        </button>
                                        <button 
                                            type="button" 
                                            onClick={handleConnectOutlook}
                                            className="connect-btn outlook-btn"
                                        >
                                            Connect to Outlook
                                        </button>
                                    </div>
                                </div>

                                {/* Group Selection */}
                                {showGroupSelection && (
                                    <div className="form-group">
                                        <label htmlFor="emailGroup" className="form-label">Select Email Group</label>
                                        <select 
                                            id="emailGroup" 
                                            name="emailGroup" 
                                            value={formData.emailGroup}
                                            onChange={handleInputChange}
                                            className="form-select"
                                        >
                                            <option value="">Select a Group</option>
                                            {emailGroups.map(group => (
                                                <option key={group.id} value={group.id}>
                                                    {group.name}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                )}

                                <button type="submit" className="submit-btn">
                                    Schedule Survey - For Demo Purposes Only
                                </button>
                            </form>
                        </div>
                    </main>
                </div>
            </div>
        </>
    );
}

export default ScheduleSurvey;