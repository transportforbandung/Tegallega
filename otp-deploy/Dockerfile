FROM opentripplanner/opentripplanner:latest

COPY routers /app/routers
COPY start.sh /app/start.sh

WORKDIR /app
RUN chmod +x start.sh

CMD ["./start.sh"]
