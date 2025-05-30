#!/bin/bash
# Download OTP JAR if not already present
if [ ! -f otp.jar ]; then
  curl -L -o otp.jar https://repo1.maven.org/maven2/org/opentripplanner/otp/2.7.0/otp-2.7.0-shaded.jar
fi

chmod +x otp.jar

# Start OTP server
java -Xmx1G -jar otp.jar --load ./ --serve
