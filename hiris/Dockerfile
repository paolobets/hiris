ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Copy application source and entrypoint
COPY app/ /usr/lib/hiris/app/
COPY run.sh /usr/lib/hiris/run.sh
RUN chmod +x /usr/lib/hiris/run.sh

# Internal port — accessed only via HA Supervisor Ingress
EXPOSE 8099

WORKDIR /usr/lib/hiris
CMD ["/usr/lib/hiris/run.sh"]
