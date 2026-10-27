# Use official slim Python runtime
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DEMO_MODE=True

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Generate sample dataset if not present
RUN python -c "from src.generate_sample import generate_sample_csv; from pathlib import Path; generate_sample_csv(Path('data/sample_household_power.csv'))"

# Expose port (Streamlit default or Cloud Run $PORT)
EXPOSE 8080

# Healthcheck
HEALTHCHECK CMD curl --fail http://localhost:8080/_stcore/health || exit 1

# Launch Streamlit with production configuration
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true", "--browser.serverAddress=0.0.0.0", "--theme.base=dark"]
