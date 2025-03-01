#!/bin/bash
eval $(/opt/homebrew/bin/brew shellenv)

# Create the wallpaper
$HOMEBREW_PREFIX/bin/solarpaper

# Set the wallpaper
$HOMEBREW_PREFIX/bin/wallpaper set ~/.cache/solarpaper/output*.png --scale fill

# Remove the old wallpaper
sleep 1
rm ~/.cache/solarpaper/output*.png
