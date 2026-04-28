import os

# Allow unauthenticated non-ingress requests in the test suite.
# The middleware deny-by-default is for production safety; tests hit the server
# directly without HA Supervisor Ingress forwarding X-Ingress-Path.
os.environ.setdefault("HIRIS_ALLOW_NO_TOKEN", "1")
