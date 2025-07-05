# Use Python base image optimized for Cloud Run
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install necessary system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install uv for dependency management
RUN pip install uv

# Install project dependencies
RUN uv sync --frozen

# Copy source code
COPY src/ /app/src/

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Set environment variables for Cloud Run Jobs
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Command to run the job (no web server needed)
CMD ["python", "src/cloud_run_okrs_job.py"] 