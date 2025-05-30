FROM eclipse-temurin:21-jdk

WORKDIR /app

# Download OTP JAR directly (adjust URL to correct OTP version if needed)
RUN curl -L -o otp.jar https://repo1.maven.org/maven2/org/opentripplanner/otp/2.7.0/otp-2.7.0-shaded.jar

# Copy graph into container
COPY routers/default/graph.obj /app/routers/default/graph.obj

EXPOSE 8080

CMD ["java", "-Xmx1G", "-jar", "otp.jar", "--load", "/app", "--serve"]
