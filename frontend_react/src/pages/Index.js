import React, {useState, useEffect} from 'react';
import ReactDOM from 'react-dom/client';
import '../assets/index.css';
import { Helmet } from 'react-helmet';
import api from '../api'

export const getUserStatus = async () => {
  try {
      const response = await api.get('/api/user/');
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
        <meta charset="UTF-8" />
        {/* Remove this line - viewport is already in public/index.html */}
        {/* <meta name="viewport" content="width=device-width, initial-scale=1.0" /> */}
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-QGYF622KGW"></script>
        <script>
            {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', 'G-QGYF622KGW');
            `}
        </script>
        <title>Sowfee Health - Mental Health Solutions for Universities</title>
        </Helmet>
      );
}

function Hero() {
    return (
        <section className="hero">
          <div className="hero-content">
            <h1>Proactive Mental Health Support for Universities.</h1>
            <p className="subheading">
              Sowfee Health offers universities a comprehensive mental health audit through real-time surveys, helping them identify and support students who may need assistance.
            </p>
            <div className="cta-group">
              <a href="#demo" className="cta-button">Watch Demo</a>
              <a href="#contact" className="cta-button outline">Get a Quote</a>
            </div>
          </div>
        </section>
    );
}

 // Helper function to get cookie value
const getCookie = (name) => {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
};

function Header() {
  const [isSuperUser, setIsSuperUser] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isInstitutionAdmin, setIsInstitutionAdmin] = useState(false);
  const [userEmail, setUserEmail] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);

  const checkAuthStatus = async () => {
      const token = getCookie('auth_token') || localStorage.getItem('auth_token');
      const emailFromCookie = getCookie('user_email') || localStorage.getItem('user_email');
      const isSuperUserCookie = getCookie('is_superuser') || localStorage.getItem('is_superuser');
      const isInstitutionAdminCookie = getCookie('is_institution_admin') || localStorage.getItem('is_institution_admin');
      
      if (token && emailFromCookie){
        setIsAuthenticated(true);
        setIsSuperUser(isSuperUserCookie === 'true');
        setUserEmail(emailFromCookie);
        setIsInstitutionAdmin(isInstitutionAdminCookie === 'true');
        return;
      }
      try {
        const data = await getUserStatus();
        setIsAuthenticated(data.is_authenticated || data.is_superuser);
        setIsSuperUser(data.is_superuser);
        setUserEmail(data.email);
        setIsInstitutionAdmin(data.is_institution_admin);
      }
      catch (error) {
        console.error('Error fetching user status:', error);
      };
    }

  // Fetch data --> 1.)
  useEffect(() => {
    checkAuthStatus();
}, []);

  
  const handleLogout = async () => {
    try {
      // Call Django logout endpoint
      await api.post('/api/logout/');
      
      // Clear local state
      setIsAuthenticated(false);
      setUserEmail('');
      setIsSuperUser(false);
      setIsInstitutionAdmin(false);
      
      // Redirect to home
      window.location.href = '/';
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  return (<header>
        <div className="logo">Sowfee</div>
        <nav className="nav-auth">
            {!isAuthenticated && (
                <a href="/demo-survey/" className="cta-button">Demo Survey</a>
            )}
            <div id="auth-container">
                {!isAuthenticated && <a href="/login/" className="cta-button outline" id="login-button">Login</a>}
                {isAuthenticated && !isSuperUser && <a href="#" className="cta-button" id="user-button" onClick={(e)=>{e.preventDefault(); setShowDropdown(!showDropdown);}}>
                    <span id="user-email">{userEmail}</span> ▼
                </a>}
                {isSuperUser && (
                  <button className="cta-button outline" id="admin-button"> Logged in as Superuser </button>
                )}
                <div id="dropdown-menu" style={{ display: showDropdown ? 'block' : 'none' }}>
                    <a href="#" id="logout-button" onClick={async (e) => {
                      e.preventDefault();
                      await handleLogout();
                    }}>Logout</a>
                    {/* Display dashboard to admins and superusers */}
                    {isAuthenticated && (!isSuperUser && isInstitutionAdmin) && (
                      <div>
                        <a href="/dashboard/" id="dashboard-button">Dashboard</a>
                        <a href="/api/admin/survey-templates/" id="edit-templates-button">Edit Templates</a>
                        <a href="/survey/" id="survey-button">Preview Survey</a>
                      </div>
                     )}
                    {isAuthenticated && (!isSuperUser && !isInstitutionAdmin) && (<a href="/survey/" id="survey-button">New Survey</a>)}
                </div>
            </div>
        </nav>
    </header>)
}

function Features () {
  return (
    <section className="features">
        <h2>Our Core Features</h2>
        <div className="features-grid">
            <div className="feature-card">
                <i className="fas fa-brain feature-icon"></i>
                <h3>Mental Health Monitoring</h3>
                <p>Track student well-being with real-time insights.</p>
            </div>
            <div className="feature-card">
                <i className="fas fa-shield-alt feature-icon"></i>
                <h3>FERPA Compliance</h3>
                <p>Ensure student privacy with secure and confidential data handling.</p>
            </div>
            <div className="feature-card">
                <i className="fas fa-chart-line feature-icon"></i>
                <h3>Data-Driven Insights</h3>
                <p>Visualize trends and improve decision-making with actionable data.</p>
            </div>
            <div className="feature-card">
                <i className="fas fa-comments feature-icon"></i>
                <h3>Instant Feedback for Students</h3>
                <p>Quickly gather student insights to respond to their needs effectively.</p>
            </div>
            <div className="feature-card">
                <i className="fas fa-mobile-alt feature-icon"></i>
                <h3>Easy Access to Surveys</h3>
                <p>Streamline survey participation with user-friendly access for students.</p>
            </div>
            <div className="feature-card">
                <i className="fas fa-graduation-cap feature-icon"></i>
                <h3>Student Success</h3>
                <p>Empower students to succeed with proactive mental health initiatives.</p>
            </div>
        </div>
    </section>
  );
}

function Demo() {
  return (
      <section id="demo">
        <h2>Learn More About Our Solution!</h2>
        <p className="demo-description">
            You can view a demo survey and how it will look by clicking the button at the top right.
        </p>
        <div className="video-container">
            <iframe width="100%" height="450" src="https://www.youtube.com/embed/GAsZ57pRsvQ" 
                    frameBorder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                    allowFullScreen></iframe>
        </div>
      </section>
  )
}

function Contact() {
  return (
    <section className="contact-section" id="contact">
      <div className="contact-grid">
          <div className="contact-info">
              <h2>Why Choose Sowfee?</h2>
              <p className="subtitle">Empowering universities with actionable insights through real-time surveys</p>
              <p className="description">Sowfee Health helps universities actively support student mental health with our easy-to-use surveys. Our platform delivers real-time insights to quickly identify students in need, enabling you to take timely action while maintaining privacy and FERPA compliance. Join us in creating a more supportive and proactive campus environment.</p>
              <ul className="benefits-list">
                  <li>
                      <i className="fas fa-shield-alt"></i>
                      <span>FERPA Compliant & Secure</span>
                  </li>
                  <li>
                      <i className="fas fa-clock"></i>
                      <span>Mental Health Monitoring</span>
                  </li>
                  <li>
                      <i className="fas fa-chart-line"></i>
                      <span>Real-time Analytics</span>
                  </li>
                  <li>
                      <i className="fas fa-mobile-alt"></i>
                      <span>Easy Access to Surveys</span>
                  </li>
              </ul>
          </div>
          <form className="contact-form" action="https://formspree.io/f/xjkgrqdj" method="POST">
              <div className="form-group">
                  <input type="text" name="institution" placeholder="Institution Name *" />
              </div>
              <div className="form-group">
                  <input type="text" name="name" placeholder="Your Name *" required />
              </div>
              <div className="form-group">
                  <input type="email" name="email" placeholder="Email *" required />
              </div>
              <div className="form-group">
                  <input type="number" name="students" placeholder="Estimated Student Population (Optional)" />
              </div>
              <div className="form-group">
                  <textarea rows="5" name="message" placeholder="Message * (e.g. 'Could you send pricing details?' or 'We'd like to schedule a demo')" required></textarea>
              </div>
              <button type="submit">Send Message</button>
          </form>
      </div>
    </section>
  )
}

function Index() {
  return (
    <div>
        <Head />
        <Header />
        <Hero />
        <Features />
        <Demo />
        <Contact />
    </div>
  );
}

export default Index;