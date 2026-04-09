# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""AWS Customer Stories Gateway Target Lambda.

Provides two tools:
- search_stories: Search AWS customer success stories
- read_story: Read full content of a customer story page
"""

import json
import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from mcp_lambda import BedrockAgentCoreGatewayTargetHandler, RequestHandler
from mcp.types import JSONRPCRequest, JSONRPCResponse, JSONRPCError, ErrorData
from aws_lambda_powertools.utilities.typing import LambdaContext
from typing import Union

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

CUSTOMER_STORIES_API = (
    "https://aws.amazon.com/api/dirs/items/search"
    "?item.directoryId=solution-case-studies-cards-interactive-customer-references"
    "&sort_by=item.additionalFields.publishedDate"
    "&sort_order=desc"
    "&item.locale=en_US"
)


def _extract_content_from_html(html: str) -> str:
    if not html:
        return "<e>Empty HTML content</e>"
    soup = BeautifulSoup(html, "html.parser")
    main_content = None
    for selector in [
        "main", "article", "#main-content", ".main-content",
        "#content", ".content", "div[role='main']",
    ]:
        content = soup.select_one(selector)
        if content:
            main_content = content
            break
    if not main_content:
        main_content = soup.body if soup.body else soup

    for selector in [
        "noscript", ".prev-next", "#main-col-footer",
        ".awsdocs-page-utilities", "#tools-panel", ".doc-cookie-banner",
    ]:
        for element in main_content.select(selector):
            element.decompose()

    for tag_name in ["script", "style", "noscript", "meta", "link", "footer", "nav", "aside", "header"]:
        for tag in main_content.find_all(tag_name):
            tag.decompose()

    content = main_content.get_text(separator="\n", strip=True)
    content = re.sub(r"\n\s*\n", "\n\n", content)
    return content if content else "<e>Page failed to be simplified from HTML</e>"


def _format_result(url: str, content: str, start_index: int, max_length: int) -> str:
    original_length = len(content)
    if start_index >= original_length:
        return f"AWS Customer Story from {url}:\n\n<e>No more content available.</e>"

    end_index = min(start_index + max_length, original_length)
    truncated_content = content[start_index:end_index]
    if not truncated_content:
        return f"AWS Customer Story from {url}:\n\n<e>No more content available.</e>"

    remaining = original_length - end_index
    result = f"AWS Customer Story from {url}:\n\n{truncated_content}"
    if remaining > 0:
        result += f"\n\n<e>Content truncated. Call read_story with start_index={end_index} to get more content.</e>"
    return result


def search_stories(search_phrase: str, limit: int = 8, page: int = 0) -> str:
    limit = min(int(limit), 50)
    page = int(page)

    encoded_phrase = urllib.parse.quote(str(search_phrase))
    search_url = f"{CUSTOMER_STORIES_API}&size={limit}&page={page}&q={encoded_phrase}&q_operator=AND"

    with httpx.Client() as client:
        response = client.get(search_url, timeout=30)
        if response.status_code != 200:
            return f"Customer story search failed - status {response.status_code}"
        data = response.json()

    metadata = data.get("metadata", {})
    total_hits = metadata.get("totalHits", 0)
    items = data.get("items", [])

    if not items:
        return f'No customer stories found for "{search_phrase}". Try broader search terms.'

    results = []
    for i, item in enumerate(items):
        inner = item.get("item", {})
        fields = inner.get("additionalFields", {})
        tags = item.get("tags", [])
        tag_names = [t.get("name", "") for t in tags]

        badge_raw = fields.get("badge", "")
        if isinstance(badge_raw, dict):
            industry = ", ".join(badge_raw.get("value", []))
        elif isinstance(badge_raw, str) and badge_raw.startswith("{"):
            try:
                badge_parsed = json.loads(badge_raw)
                industry = ", ".join(badge_parsed.get("value", []))
            except (ValueError, KeyError):
                industry = badge_raw
        else:
            industry = str(badge_raw) if badge_raw else "N/A"

        headline_url = fields.get("ctaLink", "")
        if "youtube.com" in headline_url or "youtu.be" in headline_url:
            url_type = "Video"
        elif "/solutions/case-studies/" in headline_url:
            url_type = "Case Study"
        elif "/blogs/" in headline_url:
            url_type = "Blog Post"
        else:
            url_type = "Web Page"

        customer = fields.get("mediaAlt", "") or inner.get("name", "Unknown")
        results.append({
            "rank": page * limit + i + 1,
            "customer": customer,
            "headline": fields.get("title", ""),
            "summary": fields.get("body", ""),
            "industry": industry,
            "location": fields.get("location", "N/A"),
            "date": fields.get("publishedDate", ""),
            "url": headline_url,
            "url_type": url_type,
            "tags": tag_names,
        })

    lines = [
        f'Found {total_hits} customer stories for "{search_phrase}" '
        f"(page {page + 1}, results {page * limit + 1}-{page * limit + len(results)}):\n"
    ]
    for r in results:
        tags_str = ", ".join(r["tags"]) if r["tags"] else ""
        lines.append(
            f"--- #{r['rank']} {r['customer']} ---\n"
            f"  Industry: {r['industry']} | Location: {r['location']} | Date: {r['date']}\n"
            f"  Headline: {r['headline']}\n"
            f"  Summary: {r['summary']}\n"
            + (f"  Tags: {tags_str}\n" if tags_str else "")
            + f"  URL ({r['url_type']}): {r['url']}\n"
        )
    if total_hits > (page + 1) * limit:
        lines.append(f"\n[More results available: use page={page + 1} to see next {limit} results]")
    return "\n".join(lines)


def read_story(url: str, max_length: int = 10000, start_index: int = 0) -> str:
    url_str = str(url).split("?")[0]
    if not re.match(r"^https?://(www\.)?aws\.amazon\.com/", url_str):
        return f"Invalid URL: {url_str}. Only aws.amazon.com URLs are supported."

    with httpx.Client() as client:
        response = client.get(
            url_str, follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=30,
        )
        if response.status_code >= 400:
            return f"Failed to fetch {url_str} - status code {response.status_code}"
        page_raw = response.text
        content_type = response.headers.get("content-type", "")

    if "<html" in page_raw[:100] or "text/html" in content_type or not content_type:
        content = _extract_content_from_html(page_raw)
    else:
        content = page_raw

    return _format_result(url_str, content, start_index, max_length)


# Tool dispatcher
TOOLS = {
    "search_stories": search_stories,
    "read_story": read_story,
}


class CustomerStoriesRequestHandler(RequestHandler):
    def handle_request(
        self, request: JSONRPCRequest, context: LambdaContext
    ) -> Union[JSONRPCResponse, JSONRPCError]:
        try:
            tool_name = request.params["name"]
            arguments = request.params.get("arguments", {})

            if "___" in tool_name:
                tool_name = tool_name.split("___", 1)[1]

            handler = TOOLS.get(tool_name)
            if not handler:
                return JSONRPCError(
                    jsonrpc=request.jsonrpc,
                    id=request.id,
                    error=ErrorData(code=404, message=f"Unknown tool: {tool_name}"),
                )

            result = handler(**arguments)
            return JSONRPCResponse(
                jsonrpc=request.jsonrpc,
                id=request.id,
                result={"content": [{"type": "text", "text": result}]},
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

    request_handler = CustomerStoriesRequestHandler()
    bedrock_handler = BedrockAgentCoreGatewayTargetHandler(request_handler)
    return bedrock_handler.handle(event, context)
