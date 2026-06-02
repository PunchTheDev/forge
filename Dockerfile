# Forge evaluation container
# Provides: Python 3.12, build123d (OCP), gmsh, CalculiX (ccx)
# All CPU-only. No GPU required.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Limit threading to avoid OCP/OpenMP segfaults in constrained containers.
ENV OMP_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    calculix-ccx \
    libgl1 \
    libglu1-mesa \
    libgomp1 \
    libxrender1 \
    libxext6 \
    libxcursor1 \
    libxfixes3 \
    libxft2 \
    libxinerama1 \
    libxrandr2 \
    libxi6 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /forge

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
# Verify OCP loads at build time; fail fast if the install is broken.
RUN python3 -c "from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut; print('OCP OK')"

COPY . .

ENTRYPOINT ["python3", "-m", "benchmark.evaluate"]
