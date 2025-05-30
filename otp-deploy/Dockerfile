FROM opentripplanner/opentripplanner:2.3.0

# Create directory structure explicitly
RUN mkdir -p /var/opentripplanner/graphs
COPY graph.obj /var/opentripplanner/graphs/

# Use the base image's entrypoint with proper arguments
CMD ["--load", "/var/opentripplanner/graphs", "--serve"]