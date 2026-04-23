import json
import asyncio
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag
from mcp_lambda import BedrockAgentCoreGatewayTargetHandler, RequestHandler
from mcp.types import JSONRPCRequest, JSONRPCResponse, JSONRPCError, ErrorData
from aws_lambda_powertools.utilities.typing import LambdaContext
from typing import Union

# --- Kiro.dev Algolia Config (dynamic, cached) ---
_algolia_config: dict | None = None


def _get_algolia_config(client: httpx.AsyncClient | None = None) -> dict:
    global _algolia_config
    if _algolia_config:
        return _algolia_config

    sync = httpx.Client(timeout=15)
    try:
        r = sync.get("https://kiro.dev/docs/", follow_redirects=True)
        js_urls = re.findall(r'src="(/_next/static/chunks/[^"]*\.js)"', r.text)
        for js_url in js_urls:
            resp = sync.get(f"https://kiro.dev{js_url}")
            text = resp.text
            app_ids = re.findall(r"appId[\"'\s:=]+[\"']([A-Z0-9]{8,})", text)
            api_keys = re.findall(r"apiKey[\"'\s:=]+[\"']([a-f0-9]{20,})", text)
            indices = re.findall(r"indexName[\"'\s:=]+[\"']([^\"']+)", text)
            if app_ids and api_keys and indices:
                _algolia_config = {
                    "url": f"https://{app_ids[0].lower()}-dsn.algolia.net/1/indexes/*/queries",
                    "params": {
                        "x-algolia-api-key": api_keys[0],
                        "x-algolia-application-id": app_ids[0],
                    },
                    "index": indices[0],
                }
                return _algolia_config
    finally:
        sync.close()

    raise RuntimeError("Failed to extract Algolia config from kiro.dev")


# --- Book of Kiro Config ---
BOOK_SITEMAP_URL = urljoin("https://kiro-community.github.io/book-of-kiro/", "sitemap.xml")


# ========== Kiro.dev (Algolia) ==========

async def search_kiro_docs(client: httpx.AsyncClient, keyword: str, limit: int = 10) -> list[dict]:
    cfg = _get_algolia_config()
    body = {
        "requests": [
            {
                "indexName": cfg["index"],
                "query": keyword,
                "params": f"hitsPerPage={limit}",
            }
        ]
    }
    resp = await client.post(cfg["url"], params=cfg["params"], json=body)
    resp.raise_for_status()
    data = resp.json()["results"][0]

    results = []
    seen = set()
    for hit in data.get("hits", []):
        url = hit.get("url", "")
        if url in seen:
            continue
        seen.add(url)

        hierarchy = hit.get("hierarchy", {})
        breadcrumb = " > ".join(
            v for k in ["lvl0", "lvl1", "lvl2", "lvl3", "lvl4", "lvl5", "lvl6"]
            if (v := hierarchy.get(k))
        )

        content = hit.get("content") or ""
        if not content:
            hl = hit.get("_highlightResult", {})
            if "content" in hl and hl["content"].get("value"):
                content = hl["content"]["value"]
        content = re.sub(r'<span class="algolia-docsearch-suggestion--highlight">(.*?)</span>', r"\1", content)

        results.append({
            "title": breadcrumb,
            "url": url,
            "snippet": content[:500] if content else "",
        })

    return results


# ========== Book of Kiro (Crawl + Search) ==========

async def _fetch_sitemap(client: httpx.AsyncClient) -> list[str]:
    resp = await client.get(BOOK_SITEMAP_URL)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text for loc in root.findall(".//s:loc", ns) if loc.text]


def _extract_content(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()

    main: Tag | None = soup.find("main") or soup.find("article") or soup.find(
        class_=re.compile(r"content|main|article|md-content", re.I)
    )
    source = main if main else soup.body or soup

    lines: list[str] = []
    for elem in source.find_all(["p", "li", "td", "th", "pre", "blockquote"] + [f"h{i}" for i in range(1, 7)]):
        text = elem.get_text(separator=" ", strip=True)
        if text and text not in lines[-3:] if lines else True:
            lines.append(text)

    return title, "\n".join(lines)


async def _crawl_page(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> tuple[str, str, str] | None:
    async with sem:
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            title, content = _extract_content(resp.text)
            return url, title, content
        except httpx.HTTPError:
            return None


async def search_book_of_kiro(client: httpx.AsyncClient, keyword: str, context_chars: int = 150, max_snippets: int = 2) -> list[dict]:
    urls = await _fetch_sitemap(client)
    sem = asyncio.Semaphore(8)
    tasks = [_crawl_page(client, url, sem) for url in urls]
    pages = [p for p in await asyncio.gather(*tasks) if p]

    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    results = []

    for url, title, content in pages:
        matches = list(pattern.finditer(content))
        if not matches:
            continue

        snippets = []
        for m in matches[:max_snippets]:
            start = max(0, m.start() - context_chars)
            end = min(len(content), m.end() + context_chars)
            snippet = content[start:end].replace("\n", " ")
            if start > 0:
                snippet = "..." + snippet
            if end < len(content):
                snippet = snippet + "..."
            snippets.append(snippet)

        results.append({
            "title": title,
            "url": url,
            "match_count": len(matches),
            "snippets": snippets,
        })

    results.sort(key=lambda r: r["match_count"], reverse=True)
    return results


# ========== Read Page ==========

def _read_static_html(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(["nav", "script", "style", "aside"]):
        tag.decompose()

    main: Tag | None = soup.find("main") or soup.find("article") or soup.find(
        class_=re.compile(r"content|main|article|md-content", re.I)
    )
    source = main if main else soup.body or soup

    lines: list[str] = []
    for el in source.find_all(["p", "li", "td", "th", "pre", "blockquote"] + [f"h{i}" for i in range(1, 7)]):
        text = el.get_text(separator=" ", strip=True)
        if text and (not lines or text != lines[-1]):
            lines.append(text)
    return "\n".join(lines)


def _read_nextjs_rsc(soup: BeautifulSoup) -> str:
    rsc_chunks: list[str] = []
    for script in soup.find_all("script"):
        s = script.string or ""
        m = re.search(r'self\.__next_f\.push\(\[1,"(.*)"\]\)', s, re.DOTALL)
        if m:
            rsc_chunks.append(m.group(1))

    full = "\n".join(rsc_chunks)
    texts: list[str] = []
    for m in re.finditer(r'\\"children\\":\\"((?:[^\\]|\\[^"])*?)\\"', full):
        t = m.group(1).replace("\\n", "\n").strip()
        if len(t) > 3 and not t.startswith("$") and not t.startswith("http") and not t.startswith("\\"):
            texts.append(t)

    seen: set[str] = set()
    unique: list[str] = []
    for t in texts:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    skip = {"Return to home", "Boooo, the page you're looking for does not exist."}
    return "\n".join(t for t in unique if t not in skip)


def read_page(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    main = soup.find("main")
    if main and len(main.get_text(strip=True)) > 100:
        content = _read_static_html(soup)
    else:
        content = _read_nextjs_rsc(soup)

    return title, content


# ========== Tool Functions ==========

def kiro_search(keyword_en: str, keyword_zh: str, limit: int = 10) -> str:
    if not keyword_en and not keyword_zh:
        return "keyword_en or keyword_zh is required"

    limit = int(limit)
    result = asyncio.run(_kiro_search_async(keyword_en, keyword_zh, limit))
    return json.dumps(result, ensure_ascii=False)


async def _kiro_search_async(keyword_en: str, keyword_zh: str, limit: int) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        kiro_task = search_kiro_docs(client, keyword_en, limit)
        book_task = search_book_of_kiro(client, keyword_zh)
        kiro_results, book_results = await asyncio.gather(kiro_task, book_task)

    return {
        "kiro_docs": {
            "source": "kiro.dev",
            "keyword": keyword_en,
            "total": len(kiro_results),
            "results": kiro_results,
        },
        "book_of_kiro": {
            "source": "kiro-community.github.io/book-of-kiro",
            "keyword": keyword_zh,
            "total": len(book_results),
            "results": book_results[:limit],
        },
    }


def kiro_read(url: str, max_length: int = 5000, start_index: int = 0) -> str:
    max_length = int(max_length)
    start_index = int(start_index)
    result = asyncio.run(_kiro_read_async(url, max_length, start_index))
    return json.dumps(result, ensure_ascii=False)


async def _kiro_read_async(url: str, max_length: int, start_index: int) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()

    title, content = read_page(resp.text)
    total_length = len(content)
    sliced = content[start_index:start_index + max_length]

    return {
        "url": url,
        "title": title,
        "total_length": total_length,
        "start_index": start_index,
        "content": sliced,
    }


# ========== Gateway Target Handler ==========

TOOLS = {
    "kiro_search": kiro_search,
    "kiro_read": kiro_read,
}


class KiroKnowledgeRequestHandler(RequestHandler):
    def handle_request(
        self, request: JSONRPCRequest, context: LambdaContext
    ) -> Union[JSONRPCResponse, JSONRPCError]:
        try:
            tool_name = request.params["name"]
            arguments = request.params.get("arguments", {})

            arguments.pop("original_query", None)

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
    print("Event:", json.dumps(event, default=str))

    request_handler = KiroKnowledgeRequestHandler()
    bedrock_handler = BedrockAgentCoreGatewayTargetHandler(request_handler)
    return bedrock_handler.handle(event, context)


# ========== Local Test ==========

if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1].startswith("http"):
        max_len = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
        start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        result = asyncio.run(_kiro_read_async(sys.argv[1], max_len, start))
    else:
        keyword_en = sys.argv[1] if len(sys.argv) > 1 else "MCP"
        keyword_zh = sys.argv[2] if len(sys.argv) > 2 else "插件"
        result = asyncio.run(_kiro_search_async(keyword_en, keyword_zh, 10))
    print(json.dumps(result, indent=2, ensure_ascii=False))
