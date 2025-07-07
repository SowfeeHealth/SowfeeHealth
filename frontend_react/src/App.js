import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import Register from './pages/Register';
import Index from './pages/Index';
import Survey from './pages/Survey';

function App() {
  return (
      <Router>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/survey" element={<Survey />} />
          <Route path="/survey/link/:hashLink" element={<Survey />} />
        </Routes>
      </Router>
  );
}

export default App;
