# Use specific version - confirmed working with 2.3.0
FROM opentripplanner/opentripplanner:2.3.0

# Copy graph to standard directory
COPY graph.obj /var/opentripplanner/

# Use OTP's built-in argument handling
CMD ["--load", "/var/opentripplanner", "--serve"]