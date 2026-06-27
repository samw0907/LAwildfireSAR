# Dockerfile
# Production container for the LA Wildfire SAR pipeline.
# Includes Python dependencies, GDAL, and ESA SNAP for RTC processing.

FROM ubuntu:24.04

# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# System dependencies including GDAL
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-dev \
    python3-pip \
    gdal-bin \
    libgdal-dev \
    wget \
    unzip \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Set python3.11 as default
RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    ln -sf /usr/bin/python3 /usr/bin/python

# Install SNAP headless (GPT only)
# SNAP is required for pyroSAR RTC processing
RUN wget -q https://download.esa.int/step/snap/10_0/installers/esa-snap_sentinel_unix_10_0.sh \
    -O /tmp/snap_installer.sh && \
    chmod +x /tmp/snap_installer.sh && \
    /tmp/snap_installer.sh -q -dir /opt/snap && \
    rm /tmp/snap_installer.sh

# Add SNAP GPT to PATH
ENV PATH="/opt/snap/bin:${PATH}"

# Set working directory
WORKDIR /app

# Install Python dependencies
# GDAL version matched to system GDAL
COPY requirements.txt .
RUN GDAL_VERSION=$(gdal-config --version) && \
    pip install --no-cache-dir GDAL==${GDAL_VERSION} && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ src/
COPY scripts/ scripts/
COPY tests/ tests/
COPY config/pipeline_config.yaml config/pipeline_config.yaml

# Credentials and data are mounted at runtime — never baked into image
# Mount: -v ./config/.env:/app/config/.env:ro
# Mount: -v ./data:/app/data
# Mount: -v ./outputs:/app/outputs

CMD ["python", "-m", "scripts.run_processing"]