FROM opentripplanner/opentripplanner:latest

COPY graph.obj /var/opentripplanner/graph.obj

CMD ["java", "-Xmx2G", "-jar", "otp-shaded.jar", "--load", "--serve"]
