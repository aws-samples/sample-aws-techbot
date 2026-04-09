# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from fastmcp.server.proxy import ProxyClient
from mcp_lambda import BedrockAgentCoreGatewayTargetHandler, RequestHandler
from mcp.types import JSONRPCRequest, JSONRPCResponse, JSONRPCError, ErrorData, TextContent
from aws_lambda_powertools.utilities.typing import LambdaContext
from typing import Union
import anyio
import json

proxy = ProxyClient("https://knowledge-mcp.global.api.aws")


class HttpRequestHandler(RequestHandler):
    def __init__(self, proxy_client: ProxyClient):
        self.proxy = proxy_client

    def handle_request(
        self, request: JSONRPCRequest, context: LambdaContext
    ) -> Union[JSONRPCResponse, JSONRPCError]:
        return anyio.run(self._handle_async, request)

    async def _handle_async(self, request):
        async with self.proxy as client:
            try:
                result = await client.call_tool(
                    name=request.params["name"],
                    arguments=request.params["arguments"]
                )
                text_output = next(
                    (block.text for block in result.content if isinstance(block, TextContent)),
                    None,
                )
                text_output = json.loads(text_output)
                return JSONRPCResponse(
                    jsonrpc=request.jsonrpc,
                    id=request.id,
                    result=text_output,
                )
            except Exception as error:
                import traceback
                traceback.print_exc()
                return JSONRPCError(
                    jsonrpc=request.jsonrpc,
                    id=request.id,
                    error=ErrorData(code=500, message=str(error)),
                )


def lambda_handler(event, context):
    event.pop("original_query", None)
    print("Event:", json.dumps(event, default=str))

    request_handler = HttpRequestHandler(proxy)
    bedrock_handler = BedrockAgentCoreGatewayTargetHandler(request_handler)
    return bedrock_handler.handle(event, context)
