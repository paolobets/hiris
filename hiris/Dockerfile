ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Bust Docker layer cache on every release — update this string with each version bump
RUN echo "HIRIS v0.3.12"

# Copy application source and entrypoint
COPY app/ /usr/lib/hiris/app/
COPY run.sh /usr/lib/hiris/run.sh
RUN chmod +x /usr/lib/hiris/run.sh && \
    find /usr/lib/hiris -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# Internal port — accessed only via HA Supervisor Ingress
EXPOSE 8099

WORKDIR /usr/lib/hiris
CMD ["/usr/lib/hiris/run.sh"]
