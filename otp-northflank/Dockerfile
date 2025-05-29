FROM eclipse-temurin:17

WORKDIR /app

# Download OTP (adjust version as needed)
RUN curl -L https://github.com/opentripplanner/OpenTripPlanner/releases/download/v2.5.0/otp-2.5.0-shaded.jar -o otp.jar

COPY otp-data/ /app/otp-data/
COPY start.sh /app/start.sh

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
