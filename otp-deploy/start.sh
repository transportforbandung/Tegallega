#!/bin/bash
set -e

# Create necessary folders if not exist
mkdir -p /app/routers/default

# Copy graph to the correct place for OTP to find
cp -r ./routers /app/

# Run the official OTP jar (already provided in Docker image)
exec java -Xmx2G -jar /usr/app/otp-shaded.jar --load /app/routers/default
