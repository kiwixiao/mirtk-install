# ============================================================================
# Multi-arch Docker image for MIRTK (Medical Image Registration ToolKit)
# Original source: https://github.com/BioMedIA/MIRTK
# Supports: linux/amd64 (Intel/AMD) and linux/arm64 (Apple Silicon, Graviton)
#
# Build (single arch):
#   docker build -t mirtk:latest .
#
# Build (multi-arch + push):
#   docker buildx build --platform linux/amd64,linux/arm64 -t user/mirtk:latest --push .
#
# Run:
#   docker run --rm mirtk help
#   docker run --rm -v /path/to/data:/data mirtk register ...
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build MIRTK from source
# ---------------------------------------------------------------------------
FROM ubuntu:22.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive
ARG THREADS

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      cmake \
      python3 \
      python3-dev \
      libeigen3-dev \
      libvtk9-dev \
      libtbb-dev \
      libboost-math-dev \
      libboost-random-dev \
      libnifti-dev \
      libpng-dev \
      zlib1g-dev \
      libexpat1-dev \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY . /usr/src/mirtk

RUN NUM_CPUS=${THREADS:-$(nproc)} \
    && echo "Building with $NUM_CPUS threads" \
    && mkdir -p /usr/src/mirtk/Build \
    && cd /usr/src/mirtk/Build \
    && cmake \
      -D CMAKE_INSTALL_PREFIX=/usr/local \
      -D CMAKE_BUILD_TYPE=Release \
      -D BUILD_SHARED_LIBS=ON \
      -D BUILD_APPLICATIONS=ON \
      -D BUILD_TESTING=OFF \
      -D BUILD_DOCUMENTATION=OFF \
      -D BUILD_CHANGELOG=OFF \
      -D MODULE_Common=ON \
      -D MODULE_Numerics=ON \
      -D MODULE_Image=ON \
      -D MODULE_IO=ON \
      -D MODULE_PointSet=ON \
      -D MODULE_Transformation=ON \
      -D MODULE_Registration=ON \
      -D MODULE_Deformable=ON \
      -D MODULE_Mapping=ON \
      -D MODULE_Scripting=ON \
      -D MODULE_Viewer=OFF \
      -D MODULE_DrawEM=OFF \
      -D WITH_ARPACK=OFF \
      -D WITH_FLANN=OFF \
      -D WITH_MATLAB=OFF \
      -D WITH_NiftiCLib=ON \
      -D WITH_PNG=ON \
      -D WITH_PROFILING=ON \
      -D WITH_UMFPACK=OFF \
      -D WITH_ITK=OFF \
      -D WITH_VTK=ON \
      -D WITH_ZLIB=ON \
      -D PYTHON_EXECUTABLE=/usr/bin/python3 \
      -D DEPENDS_Python_DIR=/usr \
      -D WITH_TBB=ON \
      .. \
    && make -j $NUM_CPUS install

# ---------------------------------------------------------------------------
# Stage 2: Runtime image (no build tools)
# ---------------------------------------------------------------------------
FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

LABEL description="Medical Image Registration ToolKit (MIRTK) - multi-arch build" \
      org.opencontainers.image.source="https://github.com/BioMedIA/MIRTK" \
      org.opencontainers.image.description="Fork of BioMedIA/MIRTK with macOS and multi-arch build support"

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 \
      libvtk9.1 \
      libtbb12 \
      libboost-math1.74.0 \
      libboost-random1.74.0 \
      libniftiio2 \
      libpng16-16 \
      zlib1g \
      libexpat1 \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local /usr/local

RUN echo "/usr/local/lib/mirtk" > /etc/ld.so.conf.d/mirtk.conf && ldconfig

ENTRYPOINT ["/usr/bin/python3", "/usr/local/bin/mirtk"]
CMD ["help"]

WORKDIR /data
