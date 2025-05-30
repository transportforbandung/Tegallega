# Use Java 21 JDK base image
FROM eclipse-temurin:21-jdk

# Set working directory
WORKDIR /app

# Download the OTP jar
RUN curl -L -o otp.jar https://github.com/opentripplanner/OpenTripPlanner/releases/download/v2.7.0/otp-shaded-2.7.0.jar

# Copy the graph folder with graph.obj into the container
COPY otp-deploy/routers /app/routers

# Copy the start.sh script and make it executable
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Expose the port OTP uses (default 8080)
EXPOSE 8080

# Start OTP server with start.sh
CMD ["/app/start.sh"]