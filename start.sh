#!/bin/sh

if [ ! -f /app/otp-data/graph.obj ]; then
  echo "Graph not found. Building graph..."
  java -Xmx2G -jar /app/otp.jar --build /app/otp-data
fi

echo "Starting OTP server..."
java -Xmx2G -jar /app/otp.jar --serve --graphs /app/otp-data
