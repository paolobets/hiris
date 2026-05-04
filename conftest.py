import os

# Allow unauthenticated non-ingress requests in the test suite.
# The middleware deny-by-default is for production safety; tests hit the server
# directly without HA Supervisor Ingress forwarding X-Ingress-Path.
os.environ.setdefault("HIRIS_ALLOW_NO_TOKEN", "1")

# Disable CSRF middleware in the test suite: tests use bare TestClient that
# does not inject X-Requested-With (real browsers do, via fetch()).
os.environ.setdefault("HIRIS_ALLOW_NO_CSRF", "1")
