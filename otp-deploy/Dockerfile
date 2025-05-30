# Debugging version to find the JAR path
FROM opentripplanner/opentripplanner:2.3.0

# 1. Check common locations where the JAR might be
RUN echo "Checking possible JAR locations:" && \
    ls -l /opt/opentripplanner/ 2>/dev/null || echo "No /opt/opentripplanner" && \
    ls -l /app/ 2>/dev/null || echo "No /app" && \
    ls -l /usr/share/otp/ 2>/dev/null || echo "No /usr/share/otp" && \
    echo "Searching entire system..." && \
    find / -name 'otp-shaded.jar' 2>/dev/null

# 2. Copy your graph (will continue if JAR is found)
COPY graph.obj /var/opentripplanner/