#!/bin/bash
set -euo pipefail

# Remove any stale build dirs copied from local source
rm -rf Build build

mkdir -p build
cd build

cmake ${CMAKE_ARGS} \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_APPLICATIONS=ON \
    -DBUILD_TESTING=OFF \
    -DBUILD_DOCUMENTATION=OFF \
    -DBUILD_CHANGELOG=OFF \
    -DMODULE_Common=ON \
    -DMODULE_Numerics=ON \
    -DMODULE_Image=ON \
    -DMODULE_IO=ON \
    -DMODULE_PointSet=ON \
    -DMODULE_Transformation=ON \
    -DMODULE_Registration=ON \
    -DMODULE_Deformable=ON \
    -DMODULE_Mapping=ON \
    -DMODULE_Scripting=ON \
    -DMODULE_Viewer=ON \
    -DFLTK_DIR="${PREFIX}/share/fltk" \
    -DMODULE_DrawEM=OFF \
    -DWITH_VTK=ON \
    -DWITH_TBB=ON \
    -DWITH_ZLIB=ON \
    -DWITH_NiftiCLib=OFF \
    -DWITH_PNG=ON \
    -DWITH_PROFILING=ON \
    -DWITH_ARPACK=OFF \
    -DWITH_FLANN=OFF \
    -DWITH_UMFPACK=OFF \
    -DWITH_MATLAB=OFF \
    -DWITH_ITK=OFF \
    -DPYTHON_EXECUTABLE="${PYTHON}" \
    -Wno-dev \
    ..

make -j${CPU_COUNT}
make install
