# Sowfee Health Survey Platform

A full-stack web application built for healthcare institutions to create, customize, and manage student health surveys with advanced templating and analytics capabilities.

🌐 **Live Demo:** [sowfeehealth.com](https://sowfeehealth.com)

## Overview

This platform enables healthcare institutions to create customized survey templates for students, with features including admin dashboards, secure authentication, and real-time data management. Each survey template generates unique hashed URLs for secure distribution.

## Key Features

- **Custom Survey Builder**: Institution admins can create and customize survey templates through an intuitive interface
- **Secure Authentication**: Comprehensive user authentication system using Django's built-in framework
- **Unique Survey URLs**: Each survey template generates a unique hashed URL for secure access
- **Admin Dashboard**: Full administrative control over survey templates and user management
- **RESTful API**: Scalable backend API for efficient data handling
- **Real-time Data**: Student responses are stored and processed in real-time

## Tech Stack

**Backend:**
- Django (Python web framework)
- MySQL (Database)
- Django REST Framework (API development)
- AWS EC2 (Deployment)

**Frontend:**
- React.js (User interface)
- Modern JavaScript/ES6+

**DevOps:**
- GitHub Actions (CI/CD)
- AWS EC2 (Production deployment)

## Architecture

- **Backend API**: Django REST framework handling user authentication, survey management, and data processing
- **Database**: MySQL schemas optimized for student data and survey responses
- **Frontend**: React.js application providing admin dashboard and survey interfaces
- **Deployment**: Automated CI/CD pipeline deploying to AWS EC2

## Code Structure

- `main` branch: Backend Django application
- `nextjs-frontend` branch: React.js frontend application

## Deployment

The application is fully containerized using Docker and deployed on AWS EC2:

- **Backend**: Django application running in Docker container
- **Database**: MySQL database containerized with Docker
- **Frontend**: React.js application served from production build
- **CI/CD**: Automated deployment pipeline via GitHub Actions

## Features in Detail

### Survey Template Management
- Drag-and-drop survey builder
- Customizable question types and layouts
- Template versioning and revision history

### Security & Authentication
- Role-based access control (Admin/Student)
- Secure session management
- Protected API endpoints

### Data Management
- Efficient database schemas for scalability
- Real-time response tracking
- Data export capabilities