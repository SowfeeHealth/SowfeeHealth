// src/components/Dashboard.js
import React, { useState, useEffect } from 'react';
import '../assets/dashboard.css'; // Copy your existing CSS
import api from '../api';
import { getUserStatus } from './Index';
import {Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,        // Add this for doughnut charts
  PointElement,      // Add this for line charts  
  LineElement  } from 'chart.js';

import { Bar, Doughnut, Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
  PointElement,
  LineElement,
);

function Dashboard() {
    const [dashboardData, setDashboardData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showMore, setShowMore] = useState(false);

    const fetchDashboardData = async () => {
        try {
            setLoading(true);
            
            // Check authentication first
            const userData = await getUserStatus();
            if (!userData || !userData.email) {
                window.location.href = '/login/';
                return;
            }
            
            // Check if user is admin
            if (!userData.is_institution_admin) {
                setError('Admin access required');
                return;
            }
            
            // Fetch dashboard data
            const response = await api.get('/api/dashboard/');
            setDashboardData(response.data);
            
        } catch (error) {
            console.error('Error fetching dashboard data:', error);
            setError('Failed to load dashboard data');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchDashboardData();
    }, []);

    if (loading) return <div className="loading">Loading dashboard...</div>;
    if (error) return <div className="error-message">{error}</div>;
    if (!dashboardData) return <div>No data available</div>;

    const toggleMoreStudents = () => {
              setShowMore(!showMore);
            }
    
    const responseChartData = {
        labels: dashboardData.months || [],
        datasets: [{
            data: dashboardData.monthly_num_responses || [],
            backgroundColor: '#6936f5',
            borderRadius: 8,
            barThickness: 40,
        }]
    };

    const riskChartData = {
        labels: ["At Risk", "Stable"],
        datasets: [{
            data: [
                dashboardData.num_flagged_students || 0,
                dashboardData.num_stable_students || 0
            ],
            backgroundColor: ["#ff6b6b", "#6936f5"],
        }]
    };

    // Sleep Quality Chart (Bar) 
    const sleepChartData = {
        labels: ["Good Sleep", "Poor Sleep"],
        datasets: [{
            label: "Students",
            data: [
                dashboardData.num_good_sleep_quality || 0,
                dashboardData.num_bad_sleep_quality || 0
            ],
            backgroundColor: ["#6936f5", "#ff6b6b"],
            borderRadius: 8,
        }]
    };

    // Stress Levels Chart (Bar)
    const stressChartData = {
        labels: ["Low Stress", "Moderate Stress", "High Stress"],
        datasets: [{
            label: "Students",
            data: [
                dashboardData.num_low_stress || 0,
                dashboardData.num_moderate_stress || 0,
                dashboardData.num_high_stress || 0
            ],
            backgroundColor: ["#4caf50", "#ffc107", "#ff6b6b"],
            borderRadius: 8,
        }]
    };

    // Support Perception Chart (Line)
    const supportChartData = {
        labels: dashboardData.months || [],
        datasets: [{
            label: "Feel Supported",
            data: dashboardData.monthly_support_perception || [],
            borderColor: "#6936f5",
            tension: 0.4,
            fill: false,
        }]
    };

    // Response Rate Trend Chart (Line)
    const responseRateData = {
        labels: dashboardData.months || [],
        datasets: [{
            label: "Response Rate %",
            data: dashboardData.monthly_response_rates || [],
            borderColor: "#6936f5",
            tension: 0.4,
            fill: false,
        }]
    };

    const chartOptions = {
        responsive: true,
        plugins: {
            legend: {
                position: 'top',
            },
            title: {
                display: true,
                text: 'Monthly Survey Responses',
            },
        },
    };

    return (
        <div className="dashboard-container">
            <div className="header">
                <h1>Student Wellness Dashboard</h1>
                <p className="subtitle">
                    Comprehensive overview of student mental health data
                </p>
            </div>

            <div className="home-button-wrapper">
                <button 
                    onClick={() => window.location.href = '/'}
                    className="link-btn"
                >
                    Back to Homepage
                </button>
                <button 
                    onClick={() => window.location.href = '/admin/survey-templates/'}
                    className="link-btn"
                >
                    Edit Templates
                </button>
            </div>

            {/* Metric Cards */}
            <div className="metrics-grid">
                <div className="metric-card">
                    <div className="metric-value">{dashboardData.num_responses}</div>
                    <div className="metric-title">
                        <i className="fas fa-clipboard-check"></i> Surveys Completed
                    </div>
                </div>
                <div className="metric-card">
                    <div className="metric-value">{dashboardData.num_flagged_students}</div>
                    <div className="metric-title">
                        <i className="fas fa-exclamation-triangle"></i> Students At Risk
                    </div>
                </div>
                <div className="metric-card">
                    <div className="metric-value">{dashboardData.response_rate}%</div>
                    <div className="metric-title">
                        <i className="fas fa-check-circle"></i> Response Rate
                    </div>
                </div>
            </div>

            {/* Student Table */}
            <div className="students-table-container">
                <h2 className="chart-title">Students Requiring Immediate Support</h2>
                {dashboardData.flagged_students && dashboardData.flagged_students.length > 0 ? (
                  <div>
                    <table className="students-table">
                        <thead>
                            <tr>
                                <th>Student Name</th>
                                <th>Status</th>
                                <th>Email</th>
                            </tr>
                        </thead>
                        <tbody>
                            {!showMore ? dashboardData.flagged_students.slice(0, 3).map((student, index) => (
                                <tr key={index}>
                                    <td>{student[0]}</td>
                                    <td>
                                        <span className="status-indicator">
                                            <span className="status-dot"></span>
                                            Needs Intervention
                                        </span>
                                    </td>
                                    <td>{student[1]}</td>
                                </tr>
                            )) : dashboardData.flagged_students.map((student, index) => (
                                <tr key={index}>
                                    <td>{student[0]}</td>
                                    <td>
                                        <span className="status-indicator">
                                            <span className="status-dot"></span>
                                            Needs Intervention
                                        </span>
                                    </td>
                                    <td>{student[1]}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {dashboardData.flagged_students.length > 3 && (
                        <button className="show-more-btn" onClick={toggleMoreStudents}>
                            {showMore ? "Show Less Students" : "Show More Students"}
                        </button>
                    )}
                  </div>
                ) : (
                    <p>No students currently flagged for intervention.</p>
                )
                }
            </div>
            <div className="charts-grid">
                            {/* Monthly Responses Chart */}
                <div className="chart-card">
                    <h3 className="chart-title">Monthly Survey Responses</h3>
                    <div className="chart-container">
                        <Bar options={chartOptions} data={responseChartData} />
                    </div>
                </div>

                {/* Risk Distribution Chart */}
                <div className="chart-card">
                    <h3 className="chart-title">At-Risk vs Stable Students</h3>
                    <div className="chart-container">
                        <Doughnut data={riskChartData} />
                    </div>
                </div>

                {/* Sleep Quality Chart - Only show if has sleep questions */}
                {dashboardData.has_sleep_questions && (
                    <div className="chart-card">
                        <h3 className="chart-title">Sleep Quality Distribution</h3>
                        <div className="chart-container">
                            <Bar data={sleepChartData} />
                        </div>
                    </div>
                )}

                {/* Support Perception Chart - Only show if has support questions */}
                {dashboardData.has_support_questions && (
                    <div className="chart-card">
                        <h3 className="chart-title">Campus Support Perception</h3>
                        <div className="chart-container">
                            <Line data={supportChartData} />
                        </div>
                    </div>
                )}

                {/* Stress Chart - Only show if has stress questions */}
                {dashboardData.has_stress_questions && (
                    <div className="chart-card">
                        <h3 className="chart-title">Stress Levels Analysis</h3>
                        <div className="chart-container">
                            <Bar data={stressChartData} />
                        </div>
                    </div>
                )}

                {/* Response Rate Trend Chart */}
                <div className="chart-card">
                    <h3 className="chart-title">Response Rate Trend</h3>
                    <div className="chart-container">
                        <Line data={responseRateData} />
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Dashboard;