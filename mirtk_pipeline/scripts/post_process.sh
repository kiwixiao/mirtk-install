#!/bin/bash
# =============================================================================
# Post-processing: Generate QC videos from registration output
# Optional - requires ffmpeg only (uses native nifti_to_slices.py for PNG slices)
# =============================================================================
# Called from inside the results folder.
# Usage: post_process.sh [VIDEO_SUBDIR_NAME]
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VIDEO_DIR="./video"

if [ -n "$1" ] && [ "$1" != "." ]; then
    VIDEO_DIR="./$1"
fi

# Check dependencies
if ! command -v ffmpeg &> /dev/null; then
    echo "[WARN] ffmpeg not found. Cannot generate videos."
    exit 0
fi

if ! command -v python &> /dev/null; then
    echo "[WARN] python not found. Cannot generate PNG slices."
    exit 0
fi

userin=4Dseg
user2=4Dimage
user3=segVSimage

# Count segmentation NIfTI files in current dir (we're inside results folder)
timepoints=$(ls ./seg_*.nii.gz 2>/dev/null | wc -l)
if [ "$timepoints" -eq 0 ]; then
    echo "[WARN] No seg_*.nii.gz files found. Skipping video."
    exit 0
fi

# Create video output directory
if [ -d "$VIDEO_DIR" ]; then
    rm -rf "$VIDEO_DIR"
fi
mkdir -p "$VIDEO_DIR"

# Combine time series images into 4D
echo "[INFO] Combining segmentation masks into 4D..."
mirtk combine-images ./seg_*.nii.gz -output ./"$userin".nii.gz

echo "[INFO] Combining static images into 4D..."
mirtk combine-images ./static*.nii.gz -output ./"$user2".nii.gz

# Convert to PNG slices using native Python (replaces med2image)
echo "[INFO] Generating PNG slices from segmentation 4D..."
python "$PIPELINE_DIR/nifti_to_slices.py" -i ./"$userin".nii.gz -d ./pngMask -o "$userin"

echo "[INFO] Generating PNG slices from image 4D..."
python "$PIPELINE_DIR/nifti_to_slices.py" -i ./"$user2".nii.gz -d ./pngImage -o "$user2"

# Generate videos for x direction
xfileNumI=$(ls ./pngImage/x/*.png 2>/dev/null | wc -l)
if [ "$xfileNumI" -eq 0 ]; then
    echo "[WARN] No PNG slices found. Skipping video generation."
    exit 0
fi

xsliceI=$(($xfileNumI/$timepoints))
xfileNum=$(ls ./pngMask/x/*.png | wc -l)
xslice=$(($xfileNum/$timepoints))
instep=$(($xslice/$xsliceI))
x_s_list=($(seq -s " " -f %03g 0 $instep $(($xslice-1))))
x_s_listI=($(seq -s " " -f %03g $(($xsliceI-1))))

echo "[INFO] Generating x-direction videos..."
for i in ${x_s_list[*]}; do
    ffmpeg -framerate 5 -pattern_type glob -i \
        "./pngMask/x/${userin}*slice${i}.png" \
        -c:v libx264 -crf 15 -pix_fmt yuv420p \
        -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" \
        "$VIDEO_DIR/${userin}${i}_x.mp4" 2>/dev/null
done

for i in ${x_s_listI[*]}; do
    ffmpeg -framerate 5 -pattern_type glob -i \
        "./pngImage/x/${user2}*slice${i}.png" \
        -c:v libx264 -crf 15 -pix_fmt yuv420p \
        -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" \
        "$VIDEO_DIR/${user2}${i}_x.mp4" 2>/dev/null
done

# Overlay seg on image (x direction)
for i in ${x_s_listI[*]}; do
    if [ -f "$VIDEO_DIR/${userin}${i}_x.mp4" ] && [ -f "$VIDEO_DIR/${user2}${i}_x.mp4" ]; then
        ffmpeg -i "$VIDEO_DIR/${userin}${i}_x.mp4" \
            -i "$VIDEO_DIR/${user2}${i}_x.mp4" -filter_complex \
            "[1:v]format=rgba,colorchannelmixer=aa=0.5[fg];[0][fg]overlay,scale=iw*3:-1" \
            "$VIDEO_DIR/${user3}${i}_x.mp4" 2>/dev/null
    fi
done

# y direction
echo "[INFO] Generating y-direction videos..."
yfileNum=$(ls ./pngMask/y/*.png 2>/dev/null | wc -l)
if [ "$yfileNum" -gt 0 ]; then
    yslice=$(($yfileNum/$timepoints))
    y_s_list=($(seq -s " " -f %03g $(($yslice-1))))
    for j in ${y_s_list[*]}; do
        ffmpeg -framerate 5 -pattern_type glob -i \
            "./pngMask/y/${userin}*slice${j}.png" \
            -c:v libx264 -crf 15 -pix_fmt yuv420p \
            -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" \
            "$VIDEO_DIR/${userin}${j}_y.mp4" 2>/dev/null

        ffmpeg -framerate 5 -pattern_type glob -i \
            "./pngImage/y/${user2}*slice${j}.png" \
            -c:v libx264 -crf 15 -pix_fmt yuv420p \
            -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" \
            "$VIDEO_DIR/${user2}${j}_y.mp4" 2>/dev/null

        ffmpeg -i "$VIDEO_DIR/${userin}${j}_y.mp4" \
            -i "$VIDEO_DIR/${user2}${j}_y.mp4" -filter_complex \
            "[1:v]format=rgba,colorchannelmixer=aa=0.5[fg];[0][fg]overlay,scale=iw*3:-1" \
            "$VIDEO_DIR/${user3}${j}_y.mp4" 2>/dev/null
    done
fi

# z direction
echo "[INFO] Generating z-direction videos..."
zfileNum=$(ls ./pngMask/z/*.png 2>/dev/null | wc -l)
if [ "$zfileNum" -gt 0 ]; then
    zslice=$(($zfileNum/$timepoints))
    z_s_list=($(seq -s " " -f %03g $(($zslice-1))))
    for k in ${z_s_list[*]}; do
        ffmpeg -framerate 5 -pattern_type glob -i \
            "./pngMask/z/${userin}*slice${k}.png" \
            -c:v libx264 -crf 15 -pix_fmt yuv420p \
            -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" \
            "$VIDEO_DIR/${userin}${k}_z.mp4" 2>/dev/null

        ffmpeg -framerate 5 -pattern_type glob -i \
            "./pngImage/z/${user2}*slice${k}.png" \
            -c:v libx264 -crf 15 -pix_fmt yuv420p \
            -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" \
            "$VIDEO_DIR/${user2}${k}_z.mp4" 2>/dev/null

        ffmpeg -i "$VIDEO_DIR/${userin}${k}_z.mp4" \
            -i "$VIDEO_DIR/${user2}${k}_z.mp4" -filter_complex \
            "[1:v]format=rgba,colorchannelmixer=aa=0.5[fg];[0][fg]overlay,scale=iw*3:-1" \
            "$VIDEO_DIR/${user3}${k}_z.mp4" 2>/dev/null
    done
fi

echo "[INFO] Video generation complete. Output in: $VIDEO_DIR"
