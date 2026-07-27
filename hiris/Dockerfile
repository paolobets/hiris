ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Bust Docker layer cache on every release — update this string with each version bump
RUN echo "HIRIS v0.9.7 — hotfix thinking_budget kwarg per non-Claude runners"

# Chat via abbonamento (Piano 2B): node + Claude CLI. Alpine/musl -> ripgrep di
# sistema (il ripgrep bundle di claude e' glibc). Node 22+ e' in Alpine 3.21.
# CLI pinnato al major 2: build riproducibili (niente salto a un 3.x che
# potrebbe rompere l'addon) pur ricevendo le patch. Bumpare a mano per un major.
RUN apk add --no-cache nodejs npm libgcc libstdc++ ripgrep \
    && npm install -g @anthropic-ai/claude-code@2 \
    && npm cache clean --force
ENV USE_BUILTIN_RIPGREP=0

# Copy application source, manifest, and entrypoint
COPY app/ /usr/lib/hiris/app/
COPY config.yaml /usr/lib/hiris/config.yaml
COPY run.sh /usr/lib/hiris/run.sh
RUN chmod +x /usr/lib/hiris/run.sh && \
    find /usr/lib/hiris -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# Internal port — accessed only via HA Supervisor Ingress
EXPOSE 8099

WORKDIR /usr/lib/hiris
CMD ["/usr/lib/hiris/run.sh"]
