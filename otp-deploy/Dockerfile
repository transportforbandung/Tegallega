# Use a specific version instead of 'latest' for stability
FROM opentripplanner/opentripplanner:2.3.0

# Copy graph to OTP's expected directory
COPY graph.obj /var/opentripplanner/graph.obj

# Set working directory to where the JAR actually exists
WORKDIR /app

# Correct entrypoint with verified paths
ENTRYPOINT ["java", "-Xmx2G", "-jar", "otp-shaded.jar", "--load", "/var/opentripplanner", "--serve"]