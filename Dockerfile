FROM eclipse-temurin:17

WORKDIR /app

# Download OTP (adjust version as needed)
RUN curl -L https://github.com/opentripplanner/OpenTripPlanner/releases/download/v2.7.0/otp-shaded-2.7.0.jar -o otp.jar

COPY otp-data/ /app/otp-data/
COPY start.sh /app/start.sh

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
