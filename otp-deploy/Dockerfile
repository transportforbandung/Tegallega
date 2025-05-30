FROM opentripplanner/opentripplanner:2.2.0

COPY graph.obj /var/opentripplanner/graph.obj

# Change to the directory where the JAR is located
WORKDIR /opt/opentripplanner

# Use the correct command syntax and specify graph directory
ENTRYPOINT ["java", "-Xmx2G", "-jar", "otp-shaded.jar", "--load", "/var/opentripplanner", "--serve"]
