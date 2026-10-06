FROM registry.access.redhat.com/ubi9/python-39:latest

WORKDIR /app

# Copy dependency definition and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY main.py .

# Expose non-privileged HTTP port
EXPOSE 8080

# Enforce non-root execution (Default OpenShift arbitrary UID compliance)
USER 1001

CMD ["python", "main.py"]
