from rest_framework.throttling import AnonRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    """IP-based rate limit applied to register and login endpoints."""
    scope = "auth"
