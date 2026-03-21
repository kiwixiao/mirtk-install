# MIRTK Build Makefile for macOS (Apple Silicon M3)
# Usage: make          - configure and build
#        make build    - build only (after configure)
#        make clean    - remove build artifacts
#        make install  - install to /usr/local/mirtk

BUILD_DIR    := Build
INSTALL_DIR  := /usr/local/mirtk
NUM_CPUS     := $(shell sysctl -n hw.ncpu)

.PHONY: all configure build clean install

all: configure build

configure:
	@mkdir -p $(BUILD_DIR)
	cd $(BUILD_DIR) && cmake .. \
		-DCMAKE_BUILD_TYPE=Release \
		-DCMAKE_INSTALL_PREFIX=$(INSTALL_DIR) \
		-DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
		-DWITH_TBB=ON \
		-DWITH_VTK=ON \
		-DMODULE_Common=ON \
		-DMODULE_Numerics=ON \
		-DMODULE_Image=ON \
		-DMODULE_IO=ON \
		-DMODULE_PointSet=ON \
		-DMODULE_Transformation=ON \
		-DMODULE_Registration=ON \
		-Wno-dev

build:
	cd $(BUILD_DIR) && make -j$(NUM_CPUS)

clean:
	rm -rf $(BUILD_DIR)

install:
	cd $(BUILD_DIR) && sudo make install

# ============================================================================
# Docker targets
# ============================================================================
DOCKER_REPO      ?= xiaz9n/mirtk
DOCKER_TAG       ?= latest
DOCKER_PLATFORMS := linux/amd64,linux/arm64

.PHONY: docker-setup docker-build docker-push docker-test docker-clean

# Create buildx builder for multi-arch builds
docker-setup:
	@docker buildx inspect mirtk-builder >/dev/null 2>&1 || \
		docker buildx create --name mirtk-builder --use --driver docker-container
	docker buildx inspect --bootstrap mirtk-builder

# Build for current architecture only (loads into local docker)
docker-build:
	docker buildx build \
		--tag $(DOCKER_REPO):$(DOCKER_TAG) \
		--load .

# Build multi-arch and push to Docker Hub
docker-push: docker-setup
	docker buildx build \
		--builder mirtk-builder \
		--platform $(DOCKER_PLATFORMS) \
		--tag $(DOCKER_REPO):$(DOCKER_TAG) \
		--push .

# Smoke test the built image
docker-test:
	docker run --rm $(DOCKER_REPO):$(DOCKER_TAG) help
	docker run --rm $(DOCKER_REPO):$(DOCKER_TAG) info

# Remove buildx builder
docker-clean:
	-docker buildx rm mirtk-builder
