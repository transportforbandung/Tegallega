#!/bin/bash
cd /opt/otp
exec java -Xmx2G -jar otp-shaded.jar --load --serve
