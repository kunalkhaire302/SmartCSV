# SmartCSV – Automated ETL, Insight Generation & Chat

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/flask-3.1-lightgrey.svg" alt="Flask">
  <img src="https://img.shields.io/badge/docker-ready-brightgreen.svg" alt="Docker">
</p>

<p align="center">
  <strong>From raw CSV to actionable insights and interactive chat – automatically.</strong><br>
  SmartCSV is a production-ready SaaS application that ingests CSV files, runs a robust ETL pipeline, generates rich statistical and visual insights, allows sharing reports, and supports chatting with your data via an AI assistant.
</p>

---

## ✨ Features

- **Automated ETL**: Cleans data, deduplicates, fills missing values, and identifies/handles outliers.
- **AI Chat with Data**: Ask questions about your dataset using natural language (powered by Anthropic Claude).
- **Statistical Engine**: Calculates p-values, descriptive stats, distributions, and generates automatic correlation matrices.
- **Smart Visualizations**: Rendered dynamically with Chart.js using Glassmorphism design aesthetics.
- **Authentication & User Management**: Secure Auth using JWTs, with support for Stripe Subscriptions.
- **Quotas & Limits**: Implements usage limits and monthly quotas based on subscription tiers (Free, Pro, Team).
- **Shareable Reports**: Create public links to share insights with your team.
- **Security-First**: Built-in protection against path traversal, prompt injections, and XSS. Features strict CSP and HSTS headers.

## 🏗 Architecture

**Tech Stack**:
- **Backend**: Python 3.12, Flask, Pandas, SciPy, Scikit-learn
- **Frontend**: HTML5, Vanilla CSS3 (Dark/Light mode), JavaScript, Chart.js
- **Database**: PostgreSQL (via Supabase REST API/RPC)
- **AI**: Anthropic Claude API
- **Billing**: Stripe Checkout & Customer Portal
- **Deployment**: Docker, Gunicorn

## 🚀 Getting Started

### Prerequisites

- Python **3.12+**
- Supabase account (for PostgreSQL database)
- Stripe account (for billing, optional for dev)
- Anthropic API key (for Chat)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/kunalkhaire302/SmartCSV.git
   cd SmartCSV
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/macOS
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables**
   Copy `.env.example` to `.env` and fill in your Supabase URL/keys, Anthropic API key, and Stripe keys.
   ```bash
   cp .env.example .env
   ```

5. **Run the Flask development server**
   ```bash
   flask run --debug
   ```

6. **Open your browser**  
   Navigate to [http://localhost:5000](http://localhost:5000)

### Docker

```bash
docker build -t smartcsv .
docker run --env-file .env -p 8080:8080 smartcsv
```

## 🧪 Testing

The codebase has comprehensive automated tests covering security, ETL logic, database isolation, and billing.
To run tests locally:
```bash
pytest tests/ -v --cov=.
```

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.
