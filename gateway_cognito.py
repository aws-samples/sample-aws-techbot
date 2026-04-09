# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Cognito token helper for AgentCore Gateway authentication.

Fetches and caches an OAuth2 access token using client_credentials grant.
Usage: from gateway_cognito import token

Env vars required:
  COGNITO_USER_POOL_ID  - Cognito User Pool ID
  COGNITO_CLIENT_ID     - Cognito App Client ID
  AWS_REGION            - AWS region (default: us-west-2)
"""

import os
import time
import threading
import logging

import boto3
import requests

logger = logging.getLogger(__name__)

_cache = {"access_token": None, "expires_at": 0}
_lock = threading.Lock()


def _fetch_token() -> str:
    region = os.getenv("AWS_REGION", "us-west-2")
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    client_id = os.getenv("COGNITO_CLIENT_ID")

    if not user_pool_id or not client_id:
        raise RuntimeError("COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID must be set")

    # Get client secret via boto3 (avoids storing secret in env vars)
    cognito = boto3.client("cognito-idp", region_name=region)
    resp = cognito.describe_user_pool_client(
        UserPoolId=user_pool_id, ClientId=client_id
    )
    client_secret = resp["UserPoolClient"]["ClientSecret"]

    # Discover token endpoint from OIDC config
    discovery_url = (
        f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        f"/.well-known/openid-configuration"
    )
    discovery = requests.get(discovery_url, timeout=5).json()
    token_endpoint = discovery["token_endpoint"]

    # Fetch access token using client_credentials grant
    token_resp = requests.post(
        token_endpoint,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )
    token_resp.raise_for_status()
    data = token_resp.json()

    expires_in = data.get("expires_in", 3600)
    _cache["access_token"] = data["access_token"]
    _cache["expires_at"] = time.time() + expires_in

    logger.info(f"Cognito token fetched, expires_in={expires_in}s")
    return _cache["access_token"]


def get_token() -> str:
    """Get a valid access token, refreshing if expired or about to expire."""
    with _lock:
        if _cache["access_token"] and time.time() < _cache["expires_at"] - 60:
            return _cache["access_token"]
        return _fetch_token()


class _TokenProxy:
    """Allows `from gateway_cognito import token` to always return a fresh token."""

    def __str__(self):
        return get_token()

    def __repr__(self):
        return f"TokenProxy({get_token()[:20]}...)"

    def __format__(self, format_spec):
        return format(get_token(), format_spec)


token = _TokenProxy()
