# SPIL Container Calculator

## Requirements

Make sure [docker](https://docs.docker.com/engine/install/) installed on your system.

## Run Development Server

Initialize and activate virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

## Deployment using Docker

```bash
docker-compose up -d --build
```

Your app will running in `http://localhost:8530`