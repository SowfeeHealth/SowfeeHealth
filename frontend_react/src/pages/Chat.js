import React, { useState, useEffect, useRef } from 'react';
import api from '../api';
import '../assets/chat.css';

function Chat() {
  const [assignments, setAssignments] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const ws = useRef(null);
  const messagesEndRef = useRef(null);

  const currentUserEmail = decodeURIComponent(
  document.cookie
    .split('; ')
    .find(row => row.startsWith('user_email='))
    ?.split('=')[1] || ''
).replace(/^"|"$/g, '');

  // Load assignments
  useEffect(() => {
    const fetchAssignments = async () => {
      try {
        const res = await api.get('/api/chat/assignments/');
        setAssignments(res.data.filter(a => a.is_active));
      } catch (err) {
        setError('Failed to load conversations.');
      } finally {
        setLoading(false);
      }
    };
    fetchAssignments();
  }, []);

  // Connect WebSocket when user selected
  useEffect(() => {
    if (!selectedUser) return;

    if (ws.current) ws.current.close();
    setMessages([]);
    setConnected(false);

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const isLocalhost = window.location.hostname === 'localhost' || 
                        window.location.hostname === '127.0.0.1' ||
                        window.location.hostname === '0.0.0.0';
    const wsHost = isLocalhost ? 'localhost:8001' : window.location.host;
    ws.current = new WebSocket(`${protocol}://${wsHost}/ws/chat/${selectedUser.id}/`);

    ws.current.onopen = async () => {
      setConnected(true);
      setError(null);
      try {
        const res = await api.get(`/api/chat/messages/${selectedUser.id}/`);
        setMessages(res.data.map(m => ({
          message: m.content,
          sender_id: m.sender_id,
          sender_email: m.sender__email,
          timestamp: m.timestamp,
          message_id: m.id,
          server_seq: m.server_seq,
          client_message_id: m.client_message_id,
        })));
      } catch (err) {
        console.error('Failed to load history:', err);
      }
    };

    ws.current.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.error) { setError(data.error); return; }
      setMessages(prev => {
        if (prev.some(m => m.server_seq === data.server_seq)) return prev;
        return [...prev, data].sort((a, b) => a.server_seq - b.server_seq);
      });
    };

    ws.current.onclose = (e) => {
      setConnected(false);
      if (e.code === 4001) setError('Not authenticated. Please log in.');
      if (e.code === 4003) setError('No active assignment with this user.');
    };

    return () => { if (ws.current) ws.current.close(); };
  }, [selectedUser]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);
  
  //@todo: improve frontend user logic, do not check by eamil, check my id
  const getOtherUser = (assignment) => {
    if (assignment.counselor_email === currentUserEmail) {
      return { id: assignment.student, email: assignment.student_email, role: 'Student' };
    }
    return { id: assignment.counselor, email: assignment.counselor_email, role: 'Counselor' };
  };

  const sendMessage = (e) => {
    e.preventDefault();
    if (!input.trim() || !ws.current) return;
    const clientMessageId = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    ws.current.send(JSON.stringify({ message: input.trim(), client_message_id: clientMessageId }));
    setInput('');
  };

  if (loading) return <div className="chat-page-container"><p>Loading...</p></div>;

  return (
    <div className="chat-page-container">
      <div className="chat-sidebar">
        <div className="chat-sidebar-header">
          <h3>Conversations</h3>
          <button onClick={() => window.location.href = '/'} className="chat-back-btn">Back</button>
        </div>
        {assignments.length === 0 ? (
          <p className="chat-empty">No active conversations.</p>
        ) : (
          assignments.map(a => {
            const other = getOtherUser(a);
            const isSelected = selectedUser?.id === other.id;
            return (
              <div
                key={a.id}
                className={`chat-sidebar-item ${isSelected ? 'selected' : ''}`}
                onClick={() => setSelectedUser(other)}
              >
                <div className="chat-sidebar-name">{other.email}</div>
                <div className="chat-sidebar-role">{other.role}</div>
              </div>
            );
          })
        )}
      </div>

      <div className="chat-main">
        {!selectedUser ? (
          <div className="chat-placeholder">
            <p>Select a conversation to start chatting</p>
          </div>
        ) : (
          <>
            <div className="chat-main-header">
              <h3>{selectedUser.email}</h3>
              <span className="chat-status" style={{ backgroundColor: connected ? '#4caf50' : '#f44336' }}>
                {connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>

            {error && <div className="chat-error">{error}</div>}

            <div className="chat-messages">
              {messages.map((msg) => {
                const isMe = msg.sender_email === currentUserEmail;
                return (
                  <div key={msg.server_seq} className={`chat-bubble ${isMe ? 'mine' : 'theirs'}`}>
                    <div className="chat-sender">{isMe ? 'You' : msg.sender_email}</div>
                    <div>{msg.message}</div>
                    <div className="chat-time">
                      #{msg.server_seq} · {new Date(msg.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>

            <form onSubmit={sendMessage} className="chat-input-area">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={connected ? "Type a message..." : "Disconnected"}
                disabled={!connected}
              />
              <button type="submit" disabled={!connected || !input.trim()}>Send</button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

export default Chat;