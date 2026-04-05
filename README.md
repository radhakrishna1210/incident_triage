# 🚨 Incident Triage System

## 📌 Overview

This project is an **early-stage hackathon submission** that aims to build an automated **Incident Triage System** for engineering teams. The goal of the system is to **detect incidents, classify their severity, assign ownership, and notify relevant teams automatically**.

At its current stage, the project primarily contains the **core Python logic**, initial **Django backend setup**, and **containerization support** to help developers begin building the full application.

The architecture is designed to start as a **Modular Monolith** and later scale into **microservices** if required.

---

# 🏗 Current Project Structure

### Main Folder

```
incident_triage/
```

This folder contains the **core logic ("brain") of the system**.

### Components Currently Present

| Component            | Description                                                                                                                   |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Python Code**      | About 90% of the project logic is implemented in Python. It processes incidents and manages the internal logic of the system. |
| **Dockerfile**       | Allows the application to run inside a container so it can be deployed or run on any system easily.                           |
| **Automation Setup** | Early setup using Django to eventually create a web-based interface for the tool.                                             |

Currently, the repository includes the **core logic and setup files required to start building the complete application.**

---

# 🧠 System Architecture (Conceptual)

The architecture follows a **Modular Monolith approach using Django**, with the flexibility to evolve into **microservices later**.

```
Frontend (React / Next.js)
        │
        ▼
Backend (Django)
        │
        ▼
Database (PostgreSQL)
        │
        ▼
Task Queue (Celery + Redis)
        │
        ▼
External Integrations (Slack / PagerDuty / Microsoft Teams)
```

### Architecture Components

| Layer                     | Technology                        | Purpose                                                               |
| ------------------------- | --------------------------------- | --------------------------------------------------------------------- |
| **Frontend**              | React / Next.js                   | Provides a fast, modern dashboard for engineers to monitor incidents  |
| **Backend**               | Django                            | Core application logic and APIs                                       |
| **Database**              | PostgreSQL                        | Stores structured incident data reliably                              |
| **Task Queue**            | Celery + Redis                    | Handles background tasks like sending notifications or analyzing logs |
| **External Integrations** | Slack, PagerDuty, Microsoft Teams | Sends alerts to engineering teams                                     |

---

# ⚙ Functional Components

To convert the current project into a **fully functional system**, the following layers need to be implemented.

---

# 1️⃣ Ingestion Layer (Getting Data)

This layer allows the system to **receive incident data from external systems**.

### Webhooks

Create endpoints where external services can notify the system.

Examples:

* AWS CloudWatch
* GitHub Actions
* Monitoring tools

Example Flow:

```
External Tool → Webhook → Incident Triage System
```

### Log Scraper

A Python script that scans logs and detects error patterns.

Example:

```
500 Internal Server Error
Database Connection Timeout
```

---

# 2️⃣ Triage Engine (Core Logic)

This is the **decision-making brain** of the system.

### Severity Scorer

A rules engine (or lightweight AI model) that classifies incidents into severity levels.

| Severity             | Description                              |
| -------------------- | ---------------------------------------- |
| **SEV 1 (Critical)** | Website is completely down               |
| **SEV 2 (High)**     | Major feature is broken                  |
| **SEV 3 (Low)**      | Minor issue (e.g., typo or small UI bug) |

---

### Owner Assignment

A mapping system that assigns incidents to the correct engineers.

Example:

| Service         | Responsible Team |
| --------------- | ---------------- |
| Database        | DevOps Team      |
| Authentication  | Backend Team     |
| Payment Service | FinTech Team     |

---

# 3️⃣ Communication Layer (Action)

Once an incident is detected and classified, the system must **take action automatically**.

### Notification Bot

Automatically alerts engineers.

Example:

* Create a Slack channel for **SEV 1 incidents**
* Notify responsible engineers immediately

### Status Page

A public-facing page that informs users when an issue is being investigated.

Example message:

```
We are currently investigating an issue affecting some users.
Our team is actively working on resolving it.
```

---

# 📋 Technical Requirements (Next Development Steps)

The following features need to be implemented to build the complete system.

| Feature                     | Technology                   | Purpose                                                     |
| --------------------------- | ---------------------------- | ----------------------------------------------------------- |
| **User Authentication**     | Django Auth                  | Ensures only authorized engineers access the system         |
| **Incident History**        | PostgreSQL                   | Stores historical incident data for analysis                |
| **Real-time Updates**       | Django Channels (WebSockets) | Instantly update the dashboard when incidents arrive        |
| **Background Tasks**        | Celery                       | Handles asynchronous tasks like sending notifications       |
| **Container Orchestration** | Docker Compose               | Runs multiple services (Django, Redis, PostgreSQL) together |

---

# 📊 Current Implementation Status

| Parameter Category     | Status      | Exact Value                  |
| ---------------------- | ----------- | ---------------------------- |
| **Language**           | Implemented | Python 3.x                   |
| **Framework**          | Implemented | Django                       |
| **Containerization**   | Implemented | Docker (Dockerfile present)  |
| **Database (Current)** | Default     | SQLite (Local)               |
| **Core Logic / Rules** | Not Started | To be implemented            |
| **Frontend Dashboard** | Not Started | Planned with React / Next.js |
| **Task Queue**         | Planned     | Celery + Redis               |

---

# 🚀 Future Scope

The system can evolve into a **complete DevOps incident management platform** with:

* AI-based incident classification
* Automated root cause analysis
* Smart engineer assignment
* Predictive incident detection
* Full DevOps tool integrations

---

# 📌 Project Status

⚠ **Hackathon Prototype**

The repository currently includes:

* Core Python setup
* Django backend initialization
* Docker containerization

The full incident triage workflow **still needs to be implemented in the next development phase.**

---
