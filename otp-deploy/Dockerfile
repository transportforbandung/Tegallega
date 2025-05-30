FROM eclipse-temurin:21-jdk

WORKDIR /app

# Download OTP JAR directly (adjust URL to correct OTP version if needed)
RUN curl -L -o otp.jar https://github.com/opentripplanner/OpenTripPlanner/releases/download/v2.7.0/otp-shaded-2.7.0.jar

# Copy graph into container
COPY routers/default/graph.obj /app/routers/default/graph.obj

EXPOSE 8080

CMD ["java", "-Xmx1G", "-jar", "otp.jar", "--load", "/app", "--serve"]
