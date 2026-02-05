# Use Python slim image for smaller size
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser && \
    mkdir -p /app/instance && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8080

# Run with Gunicorn (production WSGI server)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "2", "app:app"]
