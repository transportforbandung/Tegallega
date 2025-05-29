#!/bin/bash

if [ ! -f /app/otp-data/Graph.obj ]; then
  echo "Building OTP graph..."
  java -Xmx2G -jar otp.jar --build /app/otp-data
else
  echo "Graph already built, starting server..."
fi

java -Xmx2G -jar otp.jar --load /app/otp-data --serve
