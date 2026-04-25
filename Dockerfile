# Multi-stage build for quantum-raspberry-tie deployable image
# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements-docker.txt .

# Create wheels
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements-docker.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas-dev \
    libgomp1 \
    libfreetype6 \
    libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /build/wheels /wheels

# Install Python packages from wheels
COPY requirements-docker.txt .
RUN pip install --no-cache /wheels/* && rm -rf /wheels

# Copy application files
COPY QuantumKCDemo.v0_2.py qapp.py
COPY quantum_control.py quantum_control.py
#COPY expt.qasm expt.qasm
#COPY expt12.qasm expt12.qasm
#COPY expt16.qasm expt16.qasm
#COPY expt32.qasm expt32.qasm
COPY web_dashboard.py web_dashboard.py
COPY templates/ templates/
COPY files/ /app/files/

# Create credentials directory
RUN mkdir -p /app/credentials

# Install bash for entrypoint script (before switching to non-root user)
RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/*

# Copy entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create non-root user for security
RUN useradd -m -u 1000 quantum && chown -R quantum:quantum /app

USER quantum

# Expose web dashboard port
EXPOSE 5000

# Default environment variables
ENV QUANTUM_DISPLAY_MODE=svg \
    QUANTUM_BACKEND=local \
    QUANTUM_QUBITS=5 \
    FLASK_ENV=production \
    APP_VERSION=v0.2.55 \
    SVG_OUTPUT_DIR=/app/files/svg \
    QASM_DIR=/app/files/qasm \
    CONTROL_DIR=/app/files/control

# Run both services
ENTRYPOINT ["/app/entrypoint.sh"]
