# Use specific OTP version
FROM opentripplanner/opentripplanner:2.3.0

# Copy graph to standard directory
COPY graph.obj /var/opentripplanner/

# Use official OTP entrypoint pattern
ENTRYPOINT ["java", "-Xmx2G", "-jar", "/opt/opentripplanner/otp-shaded.jar", "--load", "/var/opentripplanner", "--serve"]