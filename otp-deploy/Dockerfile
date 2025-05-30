FROM eclipse-temurin:21-jdk
WORKDIR /app

# Create basePath directory explicitly
RUN mkdir -p /app/routers

# Copy OTP JAR
COPY otp-shaded-2.7.0.jar /app/otp.jar

# Copy router directory (preserve structure)
COPY routers/default /app/routers/default/

EXPOSE 8080

CMD ["java", "-Xmx1G", "-jar", "otp.jar", "--basePath", "/app", "--router", "routers/default", "--serve", "--bindAddress", "0.0.0.0"]