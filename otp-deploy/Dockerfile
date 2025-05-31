FROM eclipse-temurin:21-jdk

WORKDIR /app

# Download the JAR from the official GitHub release
ADD https://github.com/opentripplanner/OpenTripPlanner/releases/download/v2.7.0/otp-shaded-2.7.0.jar /app/otp.jar

# Copy your local graph.obj
COPY graph.obj /app/graph.obj

EXPOSE 8080

# Start OTP server
CMD ["java", "-Xmx1G", "-jar", "otp.jar", "--load", "/app", "--serve"]
