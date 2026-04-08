"""AWS China Knowledge Gateway Target Lambda.

Provides two tools:
- get_China_available_services: Search AWS China service availability
- read_China_documentation: Fetch and read AWS China docs
"""

import json
import re
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

CHINA_SERVICES_URL = "https://www.amazonaws.cn/en/about-aws/regional-product-services/"


def _extract_content_from_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    main_content = None
    for selector in [
        "main", "article", "#main-content", ".main-content",
        "#content", ".content", "div[role='main']", "#awsdocs-content",
    ]:
        content = soup.select_one(selector)
        if content:
            main_content = content
            break
    if not main_content:
        main_content = soup.body if soup.body else soup

    for tag_name in ["script", "style", "noscript", "meta", "link", "footer", "nav", "aside", "header"]:
        for tag in main_content.find_all(tag_name):
            tag.decompose()

    content = main_content.get_text(separator="\n", strip=True)
    content = re.sub(r"\n\s*\n", "\n\n", content)
    return content


def _format_result(url: str, content: str, start_index: int, max_length: int) -> str:
    original_length = len(content)
    if start_index >= original_length:
        return f"AWS China Documentation from {url}:\n\n<e>No more content available.</e>"

    end_index = min(start_index + max_length, original_length)
    truncated_content = content[start_index:end_index]
    if not truncated_content:
        return f"AWS China Documentation from {url}:\n\n<e>No more content available.</e>"

    remaining = original_length - end_index
    result = f"AWS China Documentation from {url}:\n\n{truncated_content}"
    if remaining > 0:
        result += f"\n\n<e>Content truncated. Call read_China_documentation with start_index={end_index} to get more content.</e>"
    return result


def get_china_available_services(search_phrase: str, limit: int = 5) -> str:
    with httpx.Client() as client:
        try:
            response = client.get(
                CHINA_SERVICES_URL,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=True,
                timeout=30,
            )
        except httpx.HTTPError as e:
            return f"Failed to fetch AWS China services page: {e}"

        if response.status_code >= 400:
            return f"Failed to fetch AWS China services page - status {response.status_code}"

        html = response.text

    soup = BeautifulSoup(html, "html.parser")
    search_lower = search_phrase.lower()
    matches = []

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        row_text = " ".join(c.get_text(strip=True) for c in cells)
        if search_lower in row_text.lower():
            service_name = cells[0].get_text(strip=True) if cells else ""
            link = row.find("a", href=True)
            url = link["href"] if link else ""
            if url and not url.startswith("http"):
                url = f"https://www.amazonaws.cn{url}" if url.startswith("/") else url

            availability = []
            for cell in cells[1:]:
                text = cell.get_text(strip=True)
                if text:
                    availability.append(text)

            matches.append({
                "name": service_name,
                "availability": " | ".join(availability),
                "url": url,
            })

    if not matches:
        for element in soup.find_all(["div", "li", "a"]):
            text = element.get_text(strip=True)
            if search_lower in text.lower() and len(text) < 500:
                link = element.find("a", href=True) if element.name != "a" else element
                url = ""
                if link and link.get("href"):
                    url = link["href"]
                    if not url.startswith("http"):
                        url = f"https://www.amazonaws.cn{url}" if url.startswith("/") else url
                name = text[:200]
                if not any(m["name"] == name for m in matches):
                    matches.append({"name": name, "availability": "", "url": url})

    if not matches:
        return f'No AWS China services found matching "{search_phrase}". Try broader terms.'

    matches = matches[:limit]

    lines = [f'Found {len(matches)} AWS China service(s) matching "{search_phrase}":\n']
    for i, m in enumerate(matches, 1):
        lines.append(f"### {i}. {m['name']}")
        if m["availability"]:
            lines.append(f"  Availability: {m['availability']}")
        if m["url"]:
            lines.append(f"  URL: {m['url']}")
        lines.append("")

    return "\n".join(lines)


def read_china_documentation(url: str, max_length: int = 5000, start_index: int = 0) -> str:
    url_str = str(url).split("?")[0]

    if not re.match(r"^https?://(.*\.)?(amazonaws\.cn|aws\.amazon\.com|amazon\.com)/", url_str):
        return f"Invalid URL: {url_str}. This tool supports amazonaws.cn and aws.amazon.com URLs."

    with httpx.Client() as client:
        try:
            response = client.get(
                url_str,
                follow_redirects=True,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=30,
            )
        except httpx.HTTPError as e:
            return f"Failed to fetch {url_str}: {e}"

        if response.status_code >= 400:
            return f"Failed to fetch {url_str} - status code {response.status_code}"

        page_raw = response.text
        content_type = response.headers.get("content-type", "")

    if re.search(r"self\.location\.replace\s*\(", page_raw, re.IGNORECASE):
        return "This page contains a JavaScript redirect. Try a more specific URL."

    if "<html" in page_raw[:100] or "text/html" in content_type:
        content = _extract_content_from_html(page_raw)
    else:
        content = page_raw

    return _format_result(url_str, content, start_index, max_length)


# Tool dispatcher
TOOLS = {
    "get_China_available_services": get_china_available_services,
    "read_China_documentation": read_china_documentation,
}


class ChinaKnowledgeRequestHandler(RequestHandler):
    def handle_request(
        self, request: JSONRPCRequest, context: LambdaContext
    ) -> Union[JSONRPCResponse, JSONRPCError]:
        try:
            tool_name = request.params["name"]
            arguments = request.params.get("arguments", {})

            # Strip target prefix (e.g., "TechbotChinaKnowledge___get_China_available_services")
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

    request_handler = ChinaKnowledgeRequestHandler()
    bedrock_handler = BedrockAgentCoreGatewayTargetHandler(request_handler)
    return bedrock_handler.handle(event, context)
