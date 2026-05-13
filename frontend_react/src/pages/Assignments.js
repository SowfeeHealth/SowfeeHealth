import React, { useState, useEffect } from 'react';
import api from '../api';
import '../assets/assignments.css';

function Assignments() {
  const [assignments, setAssignments] = useState([]);
  const [students, setStudents] = useState([]);
  const [counselors, setCounselors] = useState([]);
  const [selectedCounselor, setSelectedCounselor] = useState('');
  const [selectedStudent, setSelectedStudent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [assignRes, studentsRes, counselorsRes] = await Promise.all([
        api.get('/api/chat/assignments/'),
        api.get('/api/students/'),
        api.get('/api/chat/counselors/'),
      ]);
      setAssignments(assignRes.data);
      setStudents(studentsRes.data.registered_students || []);
      setCounselors(counselorsRes.data);
    } catch (err) {
      setError('Failed to load data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const promoteStudent = async (studentId, studentEmail) => {
    if (!window.confirm(`Promote ${studentEmail} to Counselor? This cannot be undone.`)) return;
    setError(null);
    setSuccess(null);
    try {
      await api.patch(`/api/chat/users/${studentId}/promote/`);
      setSuccess(`${studentEmail} promoted to Counselor.`);
      fetchData();
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to promote user.';
      setError(msg);
    }
  };
  
  const createAssignment = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!selectedCounselor || !selectedStudent) {
      setError('Please select both a counselor and a student.');
      return;
    }

    try {
      await api.post('/api/chat/assignments/', {
        counselor: selectedCounselor,
        student: selectedStudent,
      });
      setSuccess('Assignment created successfully.');
      setSelectedCounselor('');
      setSelectedStudent('');
      fetchData();
    } catch (err) {
      const msg = err.response?.data?.error || err.response?.data?.student?.[0] || 'Failed to create assignment.';
      setError(msg);
    }
  };

  const toggleActive = async (assignment) => {
    setError(null);
    setSuccess(null);
    try {
      await api.patch(`/api/chat/assignments/${assignment.id}/`, {
        is_active: !assignment.is_active,
        version: assignment.version,
      });
      setSuccess(`Assignment ${assignment.is_active ? 'deactivated' : 'reactivated'}.`);
      fetchData();
    } catch (err) {
      if (err.response?.status === 409) {
        setError('Assignment was modified by another user. Please refresh.');
      } else {
        setError('Failed to update assignment.');
      }
    }
  };

  const deleteAssignment = async (assignment) => {
    if (!window.confirm(`Delete assignment: ${assignment.counselor_email} ↔ ${assignment.student_email}?`)) return;
    setError(null);
    try {
      await api.delete(`/api/chat/assignments/${assignment.id}/`);
      setSuccess('Assignment deleted.');
      fetchData();
    } catch (err) {
      setError('Failed to delete assignment.');
    }
  };

  if (loading) return <div className="assignments-container"><p>Loading...</p></div>;

  return (
    <div className="assignments-container">
      <div className="assignments-header">
        <h2>Manage Assignments</h2>
        <button onClick={() => window.location.href = '/dashboard'} className="assignments-back-btn">Back to Dashboard</button>
      </div>

      {error && <div className="assignments-error">{error}</div>}
      {success && <div className="assignments-success">{success}</div>}

      {/* Promote Section */}
      <div className="assignments-form-card">
        <h3>Promote Student to Counselor</h3>
        <p className="assignments-hint">Select a student to give them counselor privileges. This allows them to chat with assigned students.</p>
        <div className="assignments-promote-list">
          {students.length === 0 ? (
            <p className="assignments-empty-inline">No students available.</p>
          ) : (
            students.map(s => (
              <div key={s.id} className="assignments-promote-row">
                <span>{s.email} {s.name ? `(${s.name})` : ''}</span>
                <button onClick={() => promoteStudent(s.id, s.email)} className="promote-btn">Promote to Counselor</button>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="assignments-form-card">
        <h3>Create New Assignment</h3>
        <form onSubmit={createAssignment} className="assignments-form">
          <select value={selectedCounselor} onChange={e => setSelectedCounselor(e.target.value)}>
            <option value="">Select Counselor</option>
            {counselors.map(c => (
              <option key={c.id} value={c.id}>{c.email}</option>
            ))}
          </select>
          <select value={selectedStudent} onChange={e => setSelectedStudent(e.target.value)}>
            <option value="">Select Student</option>
            {students.map(s => (
              <option key={s.id} value={s.id}>{s.email} {s.name ? `(${s.name})` : ''}</option>
            ))}
          </select>
          <button type="submit" className="create-btn">Assign</button>
        </form>
      </div>

      <table className="assignments-table">
        <thead>
          <tr>
            <th>Counselor</th>
            <th>Student</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {assignments.length === 0 ? (
            <tr><td colSpan="4" className="assignments-empty">No assignments yet.</td></tr>
          ) : (
            assignments.map(a => (
              <tr key={a.id}>
                <td>{a.counselor_email}</td>
                <td>{a.student_email}</td>
                <td>
                  <span className={a.is_active ? 'status-active' : 'status-inactive'}>
                    {a.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td>
                  <button onClick={() => toggleActive(a)} className={a.is_active ? 'deactivate-btn' : 'activate-btn'}>
                    {a.is_active ? 'Deactivate' : 'Reactivate'}
                  </button>
                  <button onClick={() => deleteAssignment(a)} className="delete-btn">Delete</button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default Assignments;