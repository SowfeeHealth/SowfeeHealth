import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import Register from './pages/Register';
import Index from './pages/Index';
import Survey from './pages/Survey';
import DemoSurvey from './pages/Demo_survey';
import SurveyTemplates from './pages/Survey_templates';
import ScheduleSurvey from './pages/Schedule_survey';

import './assets/index.css';
import './assets/login.css';
import './assets/register.css';
import './assets/survey.css';
import './assets/dashboard.css';
import './assets/demo_survey.css';

function App() {
  return (
      <Router>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/survey" element={<Survey />} />
          <Route path="/demo-survey" element={<DemoSurvey />} />
          <Route path="/admin/survey-templates" element={<SurveyTemplates />} />
          <Route path="/survey/link/:hashLink" element={<Survey />} />
          <Route path="/schedule-survey" element={<ScheduleSurvey />} />
        </Routes>
      </Router>
  );
}

export default App;
