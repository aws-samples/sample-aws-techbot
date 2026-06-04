# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""AWS Operations Gateway Target Lambda.

Proxies the AWS Agent Toolkit MCP Server (mcp-proxy-for-aws) to provide
universal AWS API access (aws___call_aws, aws___run_script, etc.) through
the AgentCore Gateway, keeping the architecture unified with other tools.
"""

import sys
import os
import boto3
from mcp.client.stdio import StdioServerParameters
from mcp_lambda import BedrockAgentCoreGatewayTargetHandler, StdioServerAdapterRequestHandler

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
        "-c",
        "from mcp_proxy_for_aws.server import main; main()",
        os.environ.get("TOOLKIT_MCP_URL", "https://aws-mcp.us-east-1.api.aws/mcp"),
        "--metadata", f"AWS_REGION={os.environ.get('AWS_REGION', 'us-west-2')}",
    ],
    env={
        "AWS_REGION": os.environ.get("AWS_REGION", "us-west-2"),
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
