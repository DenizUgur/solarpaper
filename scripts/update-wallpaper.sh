#!/bin/bash
# Create the wallpaper
/usr/local/bin/solarpaper

# Set the wallpaper
/usr/local/bin/wallpaper set ~/.cache/solarpaper/output*.png --scale fill

# Remove the old wallpaper
sleep 1
rm ~/.cache/solarpaper/output*.png
