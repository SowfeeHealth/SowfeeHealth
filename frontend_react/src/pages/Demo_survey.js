import React, { useState, useEffect } from 'react';
import '../assets/dashboard.css';

const DemoSurvey = () => {
  const [formData, setFormData] = useState({
    student_name: '',
    school_email: '',
    q1: '',
    q2: '',
    q3: '',
    q4: '',
    q5: ''
  });

  const [progress, setProgress] = useState(0);

  const questions = [
    {
      id: 'q1',
      text: '1. How would you rate your overall well-being this week?',
      options: [
        { value: '5', label: '😊 Excellent' },
        { value: '4', label: '🙂 Good' },
        { value: '3', label: '😐 Neutral' },
        { value: '2', label: '😕 Struggling' },
        { value: '1', label: '😞 Difficult' }
      ]
    },
    {
      id: 'q2',
      text: '2. How often have you thought of self-harm?',
      options: [
        { value: '1', label: 'Never' },
        { value: '2', label: 'Rarely' },
        { value: '3', label: 'Sometimes' },
        { value: '4', label: 'Often' },
        { value: '5', label: 'Always' }
      ]
    },
    {
      id: 'q3',
      text: '3. How supported do you feel by campus resources?',
      options: [
        { value: '5', label: 'Very Supported' },
        { value: '4', label: 'Supported' },
        { value: '3', label: 'Neutral' },
        { value: '2', label: 'Unsupported' },
        { value: '1', label: 'Very Unsupported' }
      ]
    },
    {
      id: 'q4',
      text: '4. How would you rate your sleep quality?',
      options: [
        { value: '5', label: '💤 Excellent' },
        { value: '4', label: '😌 Good' },
        { value: '3', label: '🛌 Average' },
        { value: '2', label: '😣 Poor' },
        { value: '1', label: '😫 Very Poor' }
      ]
    },
    {
      id: 'q5',
      text: '5. How comfortable are you seeking mental health support?',
      options: [
        { value: '5', label: '🌟 Very Comfortable' },
        { value: '4', label: '👍 Comfortable' },
        { value: '3', label: '🤔 Neutral' },
        { value: '2', label: '😟 Uncomfortable' },
        { value: '1', label: '😰 Very Uncomfortable' }
      ]
    }
  ];

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  return (
    <div className="min-h-screen bg-gray-50 py-16 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-purple-600 mb-4">Student Wellness Check</h1>
          <p className="text-gray-600">Your feedback helps us improve student support services</p>
          <div className="mt-8 h-1.5 bg-purple-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-purple-600 to-purple-400 transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <div className="space-y-6">
          {/* Student Information */}
          <div className="bg-white rounded-xl p-8 shadow-lg">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Full Name
                </label>
                <input
                  type="text"
                  name="student_name"
                  value={formData.student_name}
                  onChange={handleInputChange}
                  required
                  className="w-full px-4 py-3 border-2 border-purple-100 rounded-lg focus:border-purple-500 focus:ring-4 focus:ring-purple-100 transition-all"
                  placeholder="Enter your full name"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  School Email
                </label>
                <input
                  type="email"
                  name="school_email"
                  value={formData.school_email}
                  onChange={handleInputChange}
                  required
                  className="w-full px-4 py-3 border-2 border-purple-100 rounded-lg focus:border-purple-500 focus:ring-4 focus:ring-purple-100 transition-all"
                  placeholder="Enter your .edu email"
                />
              </div>
            </div>
          </div>

          {/* Questions */}
          {questions.map((question) => (
            <div key={question.id} className="bg-white rounded-xl p-8 shadow-lg">
              <div className="text-lg font-medium text-gray-800 mb-6">
                {question.text}
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                {question.options.map((option) => (
                  <label 
                    key={option.value}
                    className="relative cursor-pointer"
                  >
                    <input
                      type="radio"
                      name={question.id}
                      value={option.value}
                      checked={formData[question.id] === option.value}
                      onChange={handleInputChange}
                      className="sr-only"
                      required
                    />
                    <div className={`
                      text-center p-4 border-2 rounded-lg transition-all duration-200
                      ${formData[question.id] === option.value 
                        ? 'border-purple-500 bg-purple-50 shadow-md transform -translate-y-1' 
                        : 'border-purple-100 hover:border-purple-300 hover:transform hover:-translate-y-1'
                      }
                    `}>
                      <div className="text-sm font-medium">{option.label}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          ))}

          <div className="text-center">
            <div className="bg-purple-100 text-purple-800 font-medium py-4 px-8 rounded-full inline-block">
              Demo Survey - Log in to submit a real wellness check
            </div>
            
            <p className="text-sm text-gray-500 mt-6 leading-relaxed">
              Your responses are confidential and protected by FERPA regulations.<br />
              Data will only be used to improve student support services.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DemoSurvey;