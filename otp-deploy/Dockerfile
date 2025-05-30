FROM opentripplanner/opentripplanner:latest

COPY graph.obj /var/opentripplanner/graph.obj
COPY start.sh /start.sh

RUN chmod +x /start.sh

CMD ["/start.sh"]
