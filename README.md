# Tegallega
The ETL data pipeline for Transport for Bandung's Linraya transit web app. It extracts public transport network data from OpenStreetMap (OSM), transforms it into proper General Transit Feed Specification (GTFS) format, and uses it to generate GraphQL database with the help of OpenTripPlanner (OTP).

## Workflow
* Extract public transport network's GeoJSON data from OpenStreetMap
* Transform it into GTFS, using additional information (timetable, number of trips, etc.) from Transport for Bandung
* Using OTP and OSM's road data, OTP builds a routable graph.obj for deployment into OTP server.

## Build and test graph
'java -Xmx4G -jar otp-shaded-2.7.0.jar --build --serve .
