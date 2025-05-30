FROM opentripplanner/opentripplanner:latest

COPY otp-deploy/graph.obj /var/opentripplanner/graph.obj
COPY otp-deploy/start.sh /start.sh

RUN chmod +x /start.sh

CMD ["/start.sh"]
