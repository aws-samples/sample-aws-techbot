# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import sys
import os
import boto3
from mcp.client.stdio import StdioServerParameters
from mcp_lambda import BedrockAgentCoreGatewayTargetHandler, StdioServerAdapterRequestHandler
import awslabs.aws_pricing_mcp_server.server

try:
    session = boto3.Session()
    credentials = session.get_credentials()
    AWS_ACCESS_KEY_ID = credentials.access_key
    AWS_SECRET_ACCESS_KEY = credentials.secret_key
    AWS_SESSION_TOKEN = credentials.token
    print("Successfully got AWS credentials")
except Exception as e:
    print(f"Failed to get AWS credentials: {e}")
    AWS_ACCESS_KEY_ID = None
    AWS_SECRET_ACCESS_KEY = None
    AWS_SESSION_TOKEN = None

server_params = StdioServerParameters(
    command=sys.executable,
    args=[
        "/opt/python/awslabs/aws_pricing_mcp_server/server.py",
    ],
    env={
        "FASTMCP_LOG_LEVEL": "INFO",
        "AWS_REGION": os.environ.get("AWS_REGION"),
        "UV_CACHE_DIR": "/tmp/uv_cache",
        "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
        "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
        "AWS_SESSION_TOKEN": AWS_SESSION_TOKEN,
        "PYTHONPATH": "/opt/python",
    },
)

request_handler = StdioServerAdapterRequestHandler(server_params)
event_handler = BedrockAgentCoreGatewayTargetHandler(request_handler)


def lambda_handler(event, context):
    event.pop("original_query", None)
    return event_handler.handle(event, context)
