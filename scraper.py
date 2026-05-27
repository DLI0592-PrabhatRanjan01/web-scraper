"""
Dynamic Universal Web Scraper
=============================
Works with ANY site - localhost, remote, SPA, static, API-driven.
Auto-discovers APIs, intercepts network traffic, clicks through pages,
extracts HTML/CSS/JS/Forms/Media, and deep-crawls.
MEOWWWWWWW
Usage:
    # Auto-mode: discovers everything automatically
    python scraper.py http://localhost:5173 --auto

    # Discover APIs by intercepting network requests (browser)
    python scraper.py http://localhost:5173 --discover-api

    # Click automation - click all links/buttons to discover content
    python scraper.py http://localhost:5173 --click-all

    # Deep crawl - follow all internal links
    python scraper.py https://example.com --crawl --depth 3

    # Specific scraping modes
    python scraper.py https://example.com --html --css --js --forms
    python scraper.py https://api.site.com/data --api
    python scraper.py https://example.com --all

    # Hit a discovered API with pagination
    python scraper.py http://localhost:8080/api/items --api --paginate

    # Full scan with click automation + API discovery
    python scraper.py http://localhost:3000 --auto --output full_scan.json

Examples:
    python scraper.py http://localhost:5173 --auto -o site_data.json
    python scraper.py https://jsonplaceholder.typicode.com --api --crawl-api
    python scraper.py https://quotes.toscrape.com --crawl --depth 2 --click-all
    python scraper.py http://localhost:8080 --discover-api --follow-api -o apis.json
"""

import argparse
import csv
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup, Comment


class DynamicScraper:
    """
    Universal dynamic scraper that works with any site.
    Auto-discovers APIs, handles SPAs, click automation, deep crawling.
    """

    def __init__(self, base_url, headers=None, timeout=30, verify_ssl=True, delay=0.1):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.delay = delay
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.verify = verify_ssl

        # State
        self.discovered_apis = []  # API endpoints found via network intercept
        self.discovered_links = set()
        self.visited_urls = set()
        self.api_responses = []  # Collected API data
        self.html_data = []
        self.css_data = []
        self.js_data = []
        self.form_data = []
        self.media_data = []
        self.metadata_list = []
        self.click_results = []
        self.network_log = []  # All intercepted network requests

        # Detection
        self.is_spa = False
        self.detected_api_base = None

    # ================================================================
    # AUTO MODE - Intelligent full scan
    # ================================================================

    def auto_scan(self, max_pages=50, click=True):
        """
        Fully automatic scan:
        1. Fetch the page
        2. Detect if SPA (thin HTML shell)
        3. If SPA: use browser to intercept APIs + click automation
        4. Scrape discovered APIs
        5. Extract HTML/CSS/JS/Forms
        6. Deep crawl internal links
        """
        print("=" * 70)
        print(f"  AUTO SCAN: {self.base_url}")
        print("=" * 70)

        # Step 1: Initial fetch to detect site type
        print("\n[1/5] Detecting site type...")
        site_info = self._detect_site_type()
        print(f"  Type: {'SPA (JavaScript App)' if self.is_spa else 'Static/Server-Rendered'}")
        print(f"  Content-Type: {site_info.get('content_type', 'unknown')}")
        if self.is_spa:
            print(f"  HTML size: {site_info.get('html_size', 0)} bytes (thin shell detected)")

        # Step 2: Discover APIs via network interception
        print("\n[2/5] Discovering APIs (intercepting network)...")
        try:
            self.discover_apis(click_around=click)
            print(f"  Found {len(self.discovered_apis)} API endpoints")
        except Exception as e:
            print(f"  [WARN] Browser-based discovery failed: {e}")
            print(f"  Falling back to static analysis...")
            self._discover_apis_static()

        # Step 3: Fetch all discovered APIs
        if self.discovered_apis:
            print(f"\n[3/5] Fetching {len(self.discovered_apis)} discovered APIs...")
            self.fetch_all_apis()
            print(f"  Collected {len(self.api_responses)} API responses")
        else:
            print("\n[3/5] No APIs discovered, scraping HTML directly...")

        # Step 4: Scrape HTML content (rendered if SPA)
        print("\n[4/5] Extracting page content (HTML/CSS/JS/Forms)...")
        self._scrape_page_content()

        # Step 5: Crawl internal links
        print(f"\n[5/5] Crawling internal links (max {max_pages} pages)...")
        self._crawl_links(max_pages=max_pages)

        return self._compile_results()

    def _detect_site_type(self):
        """Detect if site is SPA, static, or API."""
        info = {}
        try:
            resp = self.session.get(self.base_url, timeout=self.timeout)
            info["status"] = resp.status_code
            info["content_type"] = resp.headers.get("Content-Type", "")
            info["html_size"] = len(resp.text)

            # Check if it's an API (JSON response)
            if "application/json" in info["content_type"]:
                info["type"] = "api"
                self.detected_api_base = self.base_url
                return info

            # Check if SPA (thin HTML shell with JS bundles)
            if "text/html" in info["content_type"]:
                soup = BeautifulSoup(resp.text, "html.parser")
                body_text = soup.body.get_text(strip=True) if soup.body else ""
                scripts = soup.find_all("script", src=True)
                has_root_div = bool(soup.find("div", id=re.compile(r"root|app|__next|__nuxt")))

                # SPA indicators: small body text, root div, JS bundles
                if len(body_text) < 200 and has_root_div and len(scripts) > 0:
                    self.is_spa = True
                    info["type"] = "spa"
                elif len(body_text) < 100 and len(scripts) > 0:
                    self.is_spa = True
                    info["type"] = "spa"
                else:
                    info["type"] = "static"

            return info
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Cannot reach {self.base_url}: {e}")
            info["type"] = "unreachable"
            return info

    # ================================================================
    # API DISCOVERY - Network Interception
    # ================================================================

    def discover_apis(self, click_around=True, wait_time=5000):
        """
        Use Playwright to intercept ALL network requests.
        Discovers API endpoints the site calls.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("  [ERROR] Playwright not installed. Run: pip install playwright && python -m playwright install")
            self._discover_apis_static()
            return

        api_endpoints = {}

        with sync_playwright() as p:
            # Try headless first, fall back to system Chrome
            try:
                browser = p.chromium.launch(headless=True)
            except Exception:
                browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(
                user_agent=self.headers["User-Agent"],
                ignore_https_errors=not self.verify_ssl,
            )
            page = context.new_page()

            # Intercept all network requests
            def on_response(response):
                url = response.url
                content_type = response.headers.get("content-type", "")

                # Skip static assets
                skip_extensions = ('.js', '.css', '.png', '.jpg', '.jpeg', '.gif',
                                   '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.map')
                parsed = urlparse(url)
                if any(parsed.path.endswith(ext) for ext in skip_extensions):
                    return

                # Capture API-like responses (JSON, XML)
                is_api = (
                    "json" in content_type or
                    "xml" in content_type or
                    "/api/" in parsed.path or
                    parsed.path.startswith("/api") or
                    "graphql" in parsed.path
                )

                if is_api and response.status < 400:
                    key = f"{response.request.method}:{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    if key not in api_endpoints:
                        try:
                            body = response.text()
                            api_endpoints[key] = {
                                "url": url,
                                "method": response.request.method,
                                "status": response.status,
                                "content_type": content_type,
                                "path": parsed.path,
                                "query": parsed.query,
                                "response_size": len(body),
                                "response_preview": body[:500] if body else "",
                            }
                        except Exception:
                            api_endpoints[key] = {
                                "url": url,
                                "method": response.request.method,
                                "status": response.status,
                                "content_type": content_type,
                                "path": parsed.path,
                            }

                # Log all network activity
                self.network_log.append({
                    "url": url,
                    "method": response.request.method,
                    "status": response.status,
                    "content_type": content_type.split(";")[0],
                })

            page.on("response", on_response)

            # Navigate to the page
            try:
                page.goto(self.base_url, wait_until="networkidle", timeout=30000)
            except Exception:
                try:
                    page.goto(self.base_url, wait_until="load", timeout=30000)
                except Exception as e:
                    print(f"  [WARN] Navigation issue: {e}")

            page.wait_for_timeout(2000)

            # Click automation to trigger more API calls
            if click_around:
                self._browser_click_automation(page, api_endpoints)

            browser.close()

        self.discovered_apis = list(api_endpoints.values())

    def _browser_click_automation(self, page, api_endpoints):
        """Click links, buttons, tabs to discover hidden API calls."""
        try:
            # Get all clickable elements
            clickables = page.query_selector_all(
                "a[href], button, [role='button'], [role='tab'], "
                "[onclick], .nav-link, .tab, .menu-item, [data-toggle]"
            )

            clicked = set()
            max_clicks = 30

            for elem in clickables[:max_clicks]:
                try:
                    # Get element identifier
                    text = elem.inner_text()[:50].strip()
                    href = elem.get_attribute("href") or ""

                    # Skip external links, downloads, anchors-only
                    if href.startswith(("http://", "https://")) and urlparse(href).netloc != urlparse(self.base_url).netloc:
                        continue
                    if href.startswith(("#", "javascript:void", "mailto:", "tel:")):
                        continue

                    ident = f"{text}|{href}"
                    if ident in clicked:
                        continue
                    clicked.add(ident)

                    # Click and wait for network
                    if elem.is_visible() and elem.is_enabled():
                        elem.click(timeout=3000)
                        page.wait_for_timeout(1000)

                        # Record any new link discovered
                        if href and not href.startswith("#"):
                            full_url = urljoin(self.base_url, href)
                            self.discovered_links.add(full_url)

                except Exception:
                    continue

            # Navigate back to capture state
            try:
                page.goto(self.base_url, wait_until="networkidle", timeout=10000)
            except Exception:
                pass

        except Exception as e:
            print(f"  [WARN] Click automation partial: {e}")

    def _discover_apis_static(self):
        """Fallback: discover APIs by analyzing HTML/JS source."""
        try:
            resp = self.session.get(self.base_url, timeout=self.timeout)
            text = resp.text

            # Find API URLs in source
            api_patterns = [
                r'["\']((https?://[^"\']*?/api/[^"\']+))["\']',
                r'["\']((https?://[^"\']*?/v\d+/[^"\']+))["\']',
                r'["\'](/api/[^"\']+)["\']',
                r'["\'](/v\d+/[^"\']+)["\']',
                r'fetch\(["\']([^"\']+)["\']',
                r'axios\.\w+\(["\']([^"\']+)["\']',
                r'\.get\(["\']([^"\']+)["\']',
                r'\.post\(["\']([^"\']+)["\']',
                r'baseURL:\s*["\']([^"\']+)["\']',
                r'apiUrl:\s*["\']([^"\']+)["\']',
                r'API_BASE[_URL]*\s*[=:]\s*["\']([^"\']+)["\']',
            ]

            found_urls = set()
            for pattern in api_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    url = match[0] if isinstance(match, tuple) else match
                    if url.startswith("/"):
                        url = urljoin(self.base_url, url)
                    found_urls.add(url)

            # Also check JS bundle files
            soup = BeautifulSoup(text, "html.parser")
            for script in soup.find_all("script", src=True):
                src = urljoin(self.base_url, script["src"])
                try:
                    js_resp = self.session.get(src, timeout=10)
                    for pattern in api_patterns:
                        matches = re.findall(pattern, js_resp.text)
                        for match in matches:
                            url = match[0] if isinstance(match, tuple) else match
                            if url.startswith("/"):
                                url = urljoin(self.base_url, url)
                            found_urls.add(url)
                except Exception:
                    continue

            # Test which URLs are valid
            for url in found_urls:
                try:
                    r = self.session.get(url, timeout=5)
                    if r.status_code < 400:
                        ct = r.headers.get("Content-Type", "")
                        if "json" in ct or "xml" in ct:
                            self.discovered_apis.append({
                                "url": url,
                                "method": "GET",
                                "status": r.status_code,
                                "content_type": ct,
                                "path": urlparse(url).path,
                                "response_size": len(r.text),
                                "response_preview": r.text[:500],
                            })
                except Exception:
                    continue

            print(f"  Found {len(self.discovered_apis)} APIs via static analysis")
        except Exception as e:
            print(f"  [ERROR] Static API discovery failed: {e}")

    # ================================================================
    # API FETCHING & CRAWLING
    # ================================================================

    def fetch_all_apis(self, workers=5):
        """Fetch all discovered API endpoints and collect their data."""
        seen_urls = set()

        for api in self.discovered_apis:
            url = api["url"]
            # Remove query params for dedup (keep the full URL for fetching)
            base = urlparse(url)._replace(query="").geturl()
            if base in seen_urls:
                continue
            seen_urls.add(base)

            try:
                resp = self.session.get(url, timeout=self.timeout)
                ct = resp.headers.get("Content-Type", "")

                if "json" in ct:
                    try:
                        data = resp.json()
                        self.api_responses.append({
                            "endpoint": url,
                            "method": "GET",
                            "status": resp.status_code,
                            "data": data,
                            "item_count": len(data) if isinstance(data, list) else 1,
                        })
                    except json.JSONDecodeError:
                        self.api_responses.append({
                            "endpoint": url,
                            "method": "GET",
                            "status": resp.status_code,
                            "data": resp.text[:2000],
                            "error": "invalid_json",
                        })
                elif "xml" in ct:
                    self.api_responses.append({
                        "endpoint": url,
                        "method": "GET",
                        "status": resp.status_code,
                        "data": self._parse_xml_to_dict(resp.text),
                    })
                else:
                    self.api_responses.append({
                        "endpoint": url,
                        "method": "GET",
                        "status": resp.status_code,
                        "content_type": ct,
                        "data": resp.text[:2000],
                    })
            except Exception as e:
                self.api_responses.append({
                    "endpoint": url,
                    "error": str(e),
                })

    def crawl_api(self, base_api_url, max_depth=2, workers=5):
        """
        Crawl an API - discover sub-endpoints from list responses.
        E.g., /api/items -> finds IDs -> fetches /api/items/{id}
        """
        print(f"\n[API CRAWL] Starting from: {base_api_url}")
        all_data = []

        # Fetch the base
        try:
            resp = self.session.get(base_api_url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  [ERROR] Cannot fetch {base_api_url}: {e}")
            return []

        if isinstance(data, list):
            print(f"  Found list of {len(data)} items")
            all_data.extend(data)

            # Try to discover detail endpoints
            if data and isinstance(data[0], dict):
                # Look for ID fields
                id_field = None
                for key in ("id", "_id", "ID", "Id", "slug", "key", "uuid"):
                    if key in data[0]:
                        id_field = key
                        break

                if id_field and max_depth > 0:
                    ids = [item[id_field] for item in data if id_field in item]
                    print(f"  Found {len(ids)} IDs (field: '{id_field}'), fetching details...")

                    # Try fetching detail for first item to validate endpoint
                    test_url = f"{base_api_url.rstrip('/')}/{ids[0]}"
                    try:
                        test_resp = self.session.get(test_url, timeout=5)
                        if test_resp.status_code == 200:
                            # Detail endpoint works! Fetch all
                            detail_data = self._fetch_details_parallel(
                                base_api_url, ids, workers=workers
                            )
                            all_data = detail_data  # Replace with detailed data
                            print(f"  Fetched {len(detail_data)} detailed items")
                    except Exception:
                        pass

        elif isinstance(data, dict):
            all_data.append(data)

            # Check for nested endpoints (pagination, links)
            next_url = self._find_pagination_url(data, base_api_url)
            if next_url:
                print(f"  Found pagination, following...")
                page_data = self._follow_pagination(next_url)
                all_data.extend(page_data)

        return all_data

    def _fetch_details_parallel(self, base_url, ids, workers=5):
        """Fetch detail for each ID in parallel."""
        results = []
        base = base_url.rstrip("/")

        def fetch_one(item_id):
            url = f"{base}/{item_id}"
            try:
                if self.delay:
                    time.sleep(self.delay)
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_one, id_): id_ for id_ in ids}
            done = 0
            for future in as_completed(futures):
                done += 1
                result = future.result()
                if result:
                    results.append(result)
                if done % 50 == 0:
                    print(f"    [{done}/{len(ids)}] fetched...")

        return results

    def _find_pagination_url(self, data, current_url):
        """Find next page URL from API response."""
        # Common pagination patterns
        for key in ("next", "next_url", "nextPage", "next_page_url", "links"):
            if key in data:
                val = data[key]
                if isinstance(val, str) and val.startswith(("http", "/")):
                    return urljoin(current_url, val)
                if isinstance(val, dict) and "next" in val:
                    return urljoin(current_url, val["next"])
        return None

    def _follow_pagination(self, start_url, max_pages=20):
        """Follow pagination links."""
        all_items = []
        url = start_url
        page_count = 0

        while url and page_count < max_pages:
            try:
                resp = self.session.get(url, timeout=self.timeout)
                data = resp.json()
                page_count += 1

                if isinstance(data, list):
                    if not data:
                        break
                    all_items.extend(data)
                elif isinstance(data, dict):
                    # Try common data keys
                    for key in ("data", "results", "items", "records", "content"):
                        if key in data and isinstance(data[key], list):
                            all_items.extend(data[key])
                            break

                # Find next page
                url = self._find_pagination_url(data, url) if isinstance(data, dict) else None

                if self.delay:
                    time.sleep(self.delay)
            except Exception:
                break

        print(f"    Paginated through {page_count} pages, {len(all_items)} items")
        return all_items

    # ================================================================
    # HTML / CSS / JS SCRAPING
    # ================================================================

    def _scrape_page_content(self):
        """Scrape full page content - uses browser for SPAs."""
        if self.is_spa:
            html = self._get_rendered_html()
        else:
            try:
                resp = self.session.get(self.base_url, timeout=self.timeout)
                html = resp.text
            except Exception:
                html = ""

        if not html:
            return

        soup = BeautifulSoup(html, "html.parser")
        self._extract_html_content(soup)
        self._extract_css(soup)
        self._extract_js(soup)
        self._extract_forms(soup)
        self._extract_media(soup)
        self._extract_metadata(soup)

    def _get_rendered_html(self):
        """Get fully rendered HTML using Playwright."""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception:
                    browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(user_agent=self.headers["User-Agent"])
                page.goto(self.base_url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            print(f"  [WARN] Could not render: {e}")
            try:
                return self.session.get(self.base_url, timeout=self.timeout).text
            except Exception:
                return ""

    def _extract_html_content(self, soup):
        """Extract text, headings, paragraphs, lists."""
        # Title
        title = soup.find("title")
        if title:
            self.html_data.append({"type": "title", "text": title.get_text(strip=True)})

        # Headings
        for tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            for elem in soup.find_all(tag):
                text = elem.get_text(strip=True)
                if text:
                    self.html_data.append({"type": "heading", "level": tag, "text": text})

        # Paragraphs
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if text and len(text) > 10:
                self.html_data.append({"type": "paragraph", "text": text})

        # Tables
        for table_idx, table in enumerate(soup.find_all("table")):
            headers = []
            rows = []
            thead = table.find("thead")
            if thead:
                headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]

            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells and cells != headers:
                    if headers and len(cells) == len(headers):
                        rows.append(dict(zip(headers, cells)))
                    else:
                        rows.append(cells)

            if rows:
                self.html_data.append({
                    "type": "table",
                    "index": table_idx,
                    "headers": headers,
                    "rows": rows,
                    "row_count": len(rows),
                })

        # Links
        for a in soup.find_all("a", href=True):
            href = urljoin(self.base_url, a["href"])
            text = a.get_text(strip=True)
            if text and href:
                self.html_data.append({
                    "type": "link",
                    "text": text,
                    "url": href,
                    "is_external": urlparse(href).netloc != urlparse(self.base_url).netloc,
                })
                self.discovered_links.add(href)

        # Images
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src", "")
            if src:
                self.html_data.append({
                    "type": "image",
                    "src": urljoin(self.base_url, src),
                    "alt": img.get("alt", ""),
                })

    def _extract_css(self, soup):
        """Extract CSS: external stylesheets, internal, inline, variables."""
        # External
        for link in soup.find_all("link", rel="stylesheet"):
            href = link.get("href", "")
            if href:
                self.css_data.append({
                    "type": "external_stylesheet",
                    "url": urljoin(self.base_url, href),
                    "media": link.get("media", "all"),
                })

        # Internal
        for style in soup.find_all("style"):
            css_text = style.get_text(strip=True)
            if css_text:
                rules = self._parse_css_rules(css_text)
                self.css_data.append({
                    "type": "internal_stylesheet",
                    "content": css_text[:2000],
                    "rules_count": len(rules),
                    "rules": rules[:50],
                })

        # Inline
        for elem in soup.find_all(style=True):
            self.css_data.append({
                "type": "inline_style",
                "tag": elem.name,
                "id": elem.get("id", ""),
                "class": " ".join(elem.get("class", [])),
                "style": elem["style"],
            })

        # CSS Variables
        for style in soup.find_all("style"):
            css_text = style.get_text()
            root_match = re.search(r':root\s*\{([^}]+)\}', css_text)
            if root_match:
                variables = re.findall(r'(--[\w-]+)\s*:\s*([^;]+)', root_match.group(1))
                for name, value in variables:
                    self.css_data.append({
                        "type": "css_variable",
                        "name": name.strip(),
                        "value": value.strip(),
                    })

    def _extract_js(self, soup):
        """Extract JavaScript: external scripts, inline code, API calls found."""
        # External scripts
        for script in soup.find_all("script", src=True):
            self.js_data.append({
                "type": "external_script",
                "url": urljoin(self.base_url, script["src"]),
                "async": script.has_attr("async"),
                "defer": script.has_attr("defer"),
                "module": script.get("type") == "module",
            })

        # Inline scripts
        for idx, script in enumerate(soup.find_all("script", src=False)):
            content = (script.string or "").strip()
            if not content or script.get("type") in ("application/ld+json", "application/json"):
                continue

            analysis = self._analyze_js(content)
            self.js_data.append({
                "type": "inline_script",
                "index": idx,
                "length": len(content),
                "preview": content[:500],
                "analysis": analysis,
            })

        # Event handlers
        event_attrs = ["onclick", "onload", "onsubmit", "onchange", "onkeyup", "onfocus"]
        for attr in event_attrs:
            for elem in soup.find_all(attrs={attr: True}):
                self.js_data.append({
                    "type": "event_handler",
                    "event": attr,
                    "tag": elem.name,
                    "handler": elem[attr],
                })

    def _extract_forms(self, soup):
        """Extract all forms with inputs."""
        for form in soup.find_all("form"):
            form_info = {
                "type": "form",
                "action": urljoin(self.base_url, form.get("action", "")),
                "method": form.get("method", "GET").upper(),
                "id": form.get("id", ""),
                "inputs": [],
            }
            for inp in form.find_all(["input", "textarea", "select", "button"]):
                inp_info = {
                    "tag": inp.name,
                    "type": inp.get("type", "text"),
                    "name": inp.get("name", ""),
                    "placeholder": inp.get("placeholder", ""),
                    "required": inp.has_attr("required"),
                }
                if inp.name == "select":
                    inp_info["options"] = [
                        {"value": o.get("value", ""), "text": o.get_text(strip=True)}
                        for o in inp.find_all("option")
                    ]
                form_info["inputs"].append(inp_info)
            self.form_data.append(form_info)

    def _extract_media(self, soup):
        """Extract media elements."""
        for video in soup.find_all("video"):
            sources = [{"src": urljoin(self.base_url, s.get("src", "")), "type": s.get("type", "")}
                       for s in video.find_all("source")]
            self.media_data.append({"type": "video", "src": video.get("src", ""), "sources": sources})

        for audio in soup.find_all("audio"):
            sources = [{"src": urljoin(self.base_url, s.get("src", "")), "type": s.get("type", "")}
                       for s in audio.find_all("source")]
            self.media_data.append({"type": "audio", "src": audio.get("src", ""), "sources": sources})

        for iframe in soup.find_all("iframe"):
            self.media_data.append({
                "type": "iframe",
                "src": iframe.get("src", ""),
                "title": iframe.get("title", ""),
            })

    def _extract_metadata(self, soup):
        """Extract page metadata."""
        meta = {}
        title = soup.find("title")
        if title:
            meta["title"] = title.get_text(strip=True)

        for tag in soup.find_all("meta"):
            name = tag.get("name", tag.get("property", ""))
            content = tag.get("content", "")
            if name and content:
                meta[name] = content

        # JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                meta["json_ld"] = json.loads(script.string)
            except Exception:
                pass

        if meta:
            self.metadata_list.append(meta)

    # ================================================================
    # DEEP CRAWL
    # ================================================================

    def _crawl_links(self, max_pages=50):
        """Crawl internal links to discover more content."""
        base_domain = urlparse(self.base_url).netloc
        to_visit = deque()

        # Add discovered links
        for link in self.discovered_links:
            parsed = urlparse(link)
            if parsed.netloc == base_domain and link not in self.visited_urls:
                to_visit.append(link)

        self.visited_urls.add(self.base_url)
        pages_crawled = 0

        while to_visit and pages_crawled < max_pages:
            url = to_visit.popleft()
            if url in self.visited_urls:
                continue

            self.visited_urls.add(url)
            pages_crawled += 1

            try:
                resp = self.session.get(url, timeout=self.timeout)
                ct = resp.headers.get("Content-Type", "")

                if "json" in ct:
                    # Found an API endpoint via link
                    try:
                        data = resp.json()
                        self.api_responses.append({
                            "endpoint": url,
                            "method": "GET",
                            "status": resp.status_code,
                            "data": data,
                        })
                    except json.JSONDecodeError:
                        pass
                elif "html" in ct:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    # Find more links
                    for a in soup.find_all("a", href=True):
                        href = urljoin(url, a["href"])
                        if urlparse(href).netloc == base_domain and href not in self.visited_urls:
                            to_visit.append(href)

                if self.delay:
                    time.sleep(self.delay)
            except Exception:
                continue

        if pages_crawled > 0:
            print(f"  Crawled {pages_crawled} pages")

    # ================================================================
    # CLICK AUTOMATION (Standalone)
    # ================================================================

    def click_and_scrape(self, selectors=None, max_clicks=50, wait_between=1000):
        """
        Click through a page - buttons, links, tabs, accordions.
        Captures content revealed after each click.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[ERROR] Playwright required for click automation.")
            return []

        results = []

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception:
                browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(user_agent=self.headers["User-Agent"])
            page.goto(self.base_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)

            # Default selectors for clickable elements
            if not selectors:
                selectors = [
                    "a[href]",
                    "button",
                    "[role='button']",
                    "[role='tab']",
                    ".accordion-header",
                    ".expandable",
                    "[data-toggle]",
                    ".nav-link",
                    ".tab-link",
                    ".dropdown-toggle",
                    "details > summary",
                ]

            selector_str = ", ".join(selectors)
            elements = page.query_selector_all(selector_str)
            clicked = 0

            for elem in elements:
                if clicked >= max_clicks:
                    break

                try:
                    if not elem.is_visible() or not elem.is_enabled():
                        continue

                    # Get state before click
                    text_before = page.inner_text("body")

                    # Click
                    elem.click(timeout=3000)
                    page.wait_for_timeout(wait_between)
                    clicked += 1

                    # Get state after click
                    text_after = page.inner_text("body")
                    current_url = page.url

                    # Find new content
                    if text_after != text_before:
                        new_content = text_after[len(text_before):] if len(text_after) > len(text_before) else text_after
                        results.append({
                            "action": "click",
                            "element": elem.inner_text()[:100].strip(),
                            "url_after": current_url,
                            "new_content_preview": new_content[:500],
                            "page_html": page.content()[:5000],
                        })

                    # Navigate back if URL changed
                    if current_url != self.base_url:
                        page.go_back()
                        page.wait_for_timeout(500)

                except Exception:
                    continue

            browser.close()

        print(f"  Clicked {clicked} elements, found {len(results)} content changes")
        self.click_results = results
        return results

    # ================================================================
    # SINGLE URL SCRAPING (Simple mode)
    # ================================================================

    def scrape_url(self, url=None, method="GET", body=None, render=False):
        """Scrape a single URL - works as the simple scraper."""
        target = url or self.base_url

        if render:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    try:
                        browser = p.chromium.launch(headless=True)
                    except Exception:
                        browser = p.chromium.launch(channel="chrome", headless=True)
                    page = browser.new_page(user_agent=self.headers["User-Agent"])
                    page.goto(target, wait_until="networkidle", timeout=30000)
                    html = page.content()
                    browser.close()
                soup = BeautifulSoup(html, "html.parser")
            except Exception as e:
                print(f"[WARN] Render failed: {e}")
                resp = self.session.get(target, timeout=self.timeout)
                soup = BeautifulSoup(resp.text, "html.parser")
        else:
            try:
                if method.upper() == "GET":
                    resp = self.session.get(target, timeout=self.timeout)
                elif method.upper() == "POST":
                    json_body = None
                    if body:
                        try:
                            json_body = json.loads(body)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    resp = self.session.post(target, json=json_body, data=body if not json_body else None, timeout=self.timeout)
                elif method.upper() == "PUT":
                    json_body = None
                    if body:
                        try:
                            json_body = json.loads(body)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    resp = self.session.put(target, json=json_body, data=body if not json_body else None, timeout=self.timeout)
                elif method.upper() == "DELETE":
                    resp = self.session.delete(target, timeout=self.timeout)
                elif method.upper() == "PATCH":
                    json_body = None
                    if body:
                        try:
                            json_body = json.loads(body)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    resp = self.session.patch(target, json=json_body, data=body if not json_body else None, timeout=self.timeout)
                else:
                    resp = self.session.get(target, timeout=self.timeout)

                ct = resp.headers.get("Content-Type", "")

                # API response
                if "json" in ct or resp.text.strip().startswith(("{", "[")):
                    try:
                        return {
                            "url": target,
                            "type": "api",
                            "status": resp.status_code,
                            "api_data": resp.json(),
                        }
                    except json.JSONDecodeError:
                        pass

                if "xml" in ct:
                    return {
                        "url": target,
                        "type": "api",
                        "status": resp.status_code,
                        "api_data": self._parse_xml_to_dict(resp.text),
                    }

                soup = BeautifulSoup(resp.text, "html.parser")

            except Exception as e:
                return {"error": str(e)}

        # Extract from soup
        self._extract_html_content(soup)
        self._extract_css(soup)
        self._extract_js(soup)
        self._extract_forms(soup)
        self._extract_media(soup)
        self._extract_metadata(soup)

        return self._compile_results()

    # ================================================================
    # HELPERS
    # ================================================================

    def _parse_css_rules(self, css_text):
        """Parse CSS into rules."""
        rules = []
        for match in re.finditer(r'([^{}]+)\{([^{}]+)\}', css_text):
            selector = match.group(1).strip()
            props = {}
            for prop in match.group(2).split(";"):
                if ":" in prop:
                    k, v = prop.split(":", 1)
                    props[k.strip()] = v.strip()
            if selector:
                rules.append({"selector": selector, "properties": props})
        return rules

    def _analyze_js(self, js_text):
        """Analyze JavaScript for useful info."""
        info = {}

        # API endpoints
        apis = re.findall(r'fetch\(["\']([^"\']+)', js_text)
        apis += re.findall(r'axios\.\w+\(["\']([^"\']+)', js_text)
        apis += re.findall(r'\.ajax\([^)]*url:\s*["\']([^"\']+)', js_text)
        if apis:
            info["api_calls"] = list(set(apis))

        # Functions
        funcs = re.findall(r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()', js_text)
        func_names = [f[0] or f[1] for f in funcs]
        if func_names:
            info["functions"] = func_names[:20]

        # Imports
        imports = re.findall(r'import\s+.*?from\s+["\']([^"\']+)', js_text)
        if imports:
            info["imports"] = imports

        # Event listeners
        listeners = re.findall(r'addEventListener\(["\'](\w+)', js_text)
        if listeners:
            info["event_listeners"] = list(set(listeners))

        return info

    def _parse_xml_to_dict(self, xml_text):
        """Parse XML to a nested dict."""
        try:
            root = ET.fromstring(xml_text)
            return self._xml_elem_to_dict(root)
        except ET.ParseError:
            return {"raw": xml_text[:2000]}

    def _xml_elem_to_dict(self, elem):
        """Convert XML element to dict."""
        result = {}
        if elem.attrib:
            result["@attributes"] = dict(elem.attrib)
        if elem.text and elem.text.strip():
            if len(elem) == 0:
                return elem.text.strip()
            result["#text"] = elem.text.strip()
        for child in elem:
            child_data = self._xml_elem_to_dict(child)
            if child.tag in result:
                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_data)
            else:
                result[child.tag] = child_data
        return result or (elem.text.strip() if elem.text else "")

    def _compile_results(self):
        """Compile all scraped data into a single result dict."""
        result = {
            "url": self.base_url,
            "scan_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "is_spa": self.is_spa,
        }

        if self.discovered_apis:
            result["discovered_apis"] = self.discovered_apis
        if self.api_responses:
            result["api_data"] = self.api_responses
        if self.html_data:
            result["html_content"] = self.html_data
        if self.css_data:
            result["css"] = self.css_data
        if self.js_data:
            result["javascript"] = self.js_data
        if self.form_data:
            result["forms"] = self.form_data
        if self.media_data:
            result["media"] = self.media_data
        if self.metadata_list:
            result["metadata"] = self.metadata_list
        if self.click_results:
            result["click_automation_results"] = self.click_results
        if self.network_log:
            result["network_requests"] = len(self.network_log)

        # Summary
        result["summary"] = {
            "apis_discovered": len(self.discovered_apis),
            "api_responses_collected": len(self.api_responses),
            "html_elements": len(self.html_data),
            "css_items": len(self.css_data),
            "js_items": len(self.js_data),
            "forms": len(self.form_data),
            "media_items": len(self.media_data),
            "pages_visited": len(self.visited_urls),
            "total_network_requests": len(self.network_log),
        }

        return result


# ================================================================
# OUTPUT HELPERS
# ================================================================

def save_json(data, filename):
    """Save data to JSON."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    size = len(json.dumps(data, default=str))
    print(f"[SAVED] {filename} ({size/1024:.1f} KB)")


def save_csv(data, filename):
    """Save data to CSV (flattens nested structures)."""
    flat_rows = []

    def flatten(obj, prefix=""):
        row = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
                if isinstance(v, (dict, list)):
                    row[key] = json.dumps(v, ensure_ascii=False, default=str)[:500]
                else:
                    row[key] = v
        return row

    # Find the biggest list in data for CSV
    if isinstance(data, dict):
        # Try api_data first, then html_content
        for key in ("api_data", "html_content", "discovered_apis", "css", "javascript"):
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    if isinstance(item, dict):
                        if "data" in item and isinstance(item["data"], list):
                            for d in item["data"]:
                                flat_rows.append(flatten(d) if isinstance(d, dict) else {"value": d})
                        else:
                            flat_rows.append(flatten(item))
                break
    elif isinstance(data, list):
        for item in data:
            flat_rows.append(flatten(item) if isinstance(item, dict) else {"value": item})

    if not flat_rows:
        print("[WARN] No tabular data to save as CSV")
        return

    all_keys = set()
    for row in flat_rows:
        all_keys.update(row.keys())
    fieldnames = sorted(all_keys)

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_rows)

    print(f"[SAVED] {filename} ({len(flat_rows)} rows)")


# ================================================================
# CLI
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Dynamic Universal Web Scraper - Works with ANY site",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-scan (discovers everything automatically)
  python scraper.py http://localhost:5173 --auto
  python scraper.py https://example.com --auto -o results.json

  # Discover APIs (intercepts network traffic)
  python scraper.py http://localhost:3000 --discover-api
  python scraper.py http://localhost:8080 --discover-api --follow-api

  # Click automation (interact with page elements)
  python scraper.py http://localhost:5173 --click-all
  python scraper.py https://spa-app.com --click-all --max-clicks 100

  # API crawling (auto-discovers sub-endpoints)
  python scraper.py http://localhost:8080/api/items --crawl-api --workers 10

  # Deep crawl (follows all internal links)
  python scraper.py https://example.com --crawl --depth 5

  # Specific scraping
  python scraper.py https://example.com --html --css --js --forms
  python scraper.py https://api.github.com/users/octocat --api
  python scraper.py https://example.com --render --html

  # POST/PUT/DELETE
  python scraper.py http://localhost:8080/api/data --method POST --body '{"name":"test"}'

  # Custom headers
  python scraper.py https://api.example.com/data --header "Authorization: Bearer TOKEN"

  # Output
  python scraper.py http://localhost:5173 --auto -o scan.json -f both
        """,
    )

    parser.add_argument("url", help="Target URL (any site - localhost, remote, API, SPA)")

    # Main modes
    mode_group = parser.add_argument_group("Scan Modes")
    mode_group.add_argument("--auto", action="store_true",
                           help="Full automatic scan (detects type, discovers APIs, scrapes everything)")
    mode_group.add_argument("--discover-api", action="store_true",
                           help="Discover API endpoints by intercepting network traffic")
    mode_group.add_argument("--crawl-api", action="store_true",
                           help="Crawl an API endpoint (finds IDs, fetches details)")
    mode_group.add_argument("--follow-api", action="store_true",
                           help="After discovering APIs, fetch all their data")
    mode_group.add_argument("--click-all", action="store_true",
                           help="Click automation - interact with all buttons/links/tabs")
    mode_group.add_argument("--crawl", action="store_true",
                           help="Deep crawl - follow all internal links")
    mode_group.add_argument("--render", action="store_true",
                           help="Render page with headless browser (for SPAs)")

    # Content types
    content_group = parser.add_argument_group("Content to Extract")
    content_group.add_argument("--html", action="store_true", help="Extract HTML content (text, tables, links, images)")
    content_group.add_argument("--css", action="store_true", help="Extract CSS (stylesheets, inline, variables)")
    content_group.add_argument("--js", action="store_true", help="Extract JavaScript (scripts, event handlers)")
    content_group.add_argument("--forms", action="store_true", help="Extract forms with all inputs")
    content_group.add_argument("--media", action="store_true", help="Extract media (video, audio, iframes)")
    content_group.add_argument("--api", action="store_true", help="Treat URL as API endpoint")
    content_group.add_argument("--all", action="store_true", help="Extract everything from HTML")
    content_group.add_argument("--metadata", action="store_true", help="Extract page metadata")
    content_group.add_argument("--headers", action="store_true", help="Show HTTP response headers")

    # Options
    opt_group = parser.add_argument_group("Options")
    opt_group.add_argument("--method", default="GET", choices=["GET", "POST", "PUT", "DELETE", "PATCH"],
                          help="HTTP method (default: GET)")
    opt_group.add_argument("--body", type=str, help="Request body for POST/PUT/PATCH")
    opt_group.add_argument("--header", action="append", help="Custom header (Key: Value)")
    opt_group.add_argument("--depth", type=int, default=3, help="Crawl depth (default: 3)")
    opt_group.add_argument("--max-pages", type=int, default=50, help="Max pages to crawl (default: 50)")
    opt_group.add_argument("--max-clicks", type=int, default=50, help="Max elements to click (default: 50)")
    opt_group.add_argument("--workers", type=int, default=5, help="Parallel workers for API fetching (default: 5)")
    opt_group.add_argument("--delay", type=float, default=0.1, help="Delay between requests (default: 0.1s)")
    opt_group.add_argument("--no-verify-ssl", action="store_true", help="Disable SSL verification")
    opt_group.add_argument("--paginate", action="store_true", help="Follow API pagination")

    # Output
    out_group = parser.add_argument_group("Output")
    out_group.add_argument("--output", "-o", type=str, default="scraped_data.json",
                          help="Output file (default: scraped_data.json)")
    out_group.add_argument("--format", "-f", choices=["json", "csv", "both"], default="json",
                          help="Output format (default: json)")

    args = parser.parse_args()

    # Validate URL
    parsed = urlparse(args.url)
    if not parsed.scheme:
        args.url = "http://" + args.url
        parsed = urlparse(args.url)
    if not parsed.netloc:
        print("[ERROR] Invalid URL. Example: http://localhost:5173 or https://example.com")
        sys.exit(1)

    # Create scraper
    scraper = DynamicScraper(
        base_url=args.url,
        timeout=30,
        verify_ssl=not args.no_verify_ssl,
        delay=args.delay,
    )

    # Apply custom headers
    if args.header:
        for h in args.header:
            if ":" in h:
                key, value = h.split(":", 1)
                scraper.headers[key.strip()] = value.strip()
                scraper.session.headers[key.strip()] = value.strip()

    # Execute based on mode
    results = None

    if args.auto:
        # Full automatic scan
        results = scraper.auto_scan(max_pages=args.max_pages, click=args.click_all or True)

    elif args.discover_api:
        # Just discover APIs
        print(f"[*] Discovering APIs on {args.url}...")
        scraper.discover_apis(click_around=args.click_all)
        results = {
            "url": args.url,
            "discovered_apis": scraper.discovered_apis,
            "network_log": scraper.network_log,
            "total_apis": len(scraper.discovered_apis),
        }
        if args.follow_api and scraper.discovered_apis:
            print(f"[*] Fetching {len(scraper.discovered_apis)} discovered APIs...")
            scraper.fetch_all_apis(workers=args.workers)
            results["api_data"] = scraper.api_responses

    elif args.crawl_api:
        # Crawl an API endpoint
        data = scraper.crawl_api(args.url, max_depth=args.depth, workers=args.workers)
        results = {
            "url": args.url,
            "type": "api_crawl",
            "items": data,
            "total_items": len(data),
        }

    elif args.click_all:
        # Click automation only
        print(f"[*] Running click automation on {args.url}...")
        click_data = scraper.click_and_scrape(max_clicks=args.max_clicks)
        results = {
            "url": args.url,
            "click_results": click_data,
            "total_interactions": len(click_data),
        }

    elif args.crawl:
        # Deep crawl
        print(f"[*] Deep crawling {args.url} (depth={args.depth})...")
        scraper._detect_site_type()
        scraper._scrape_page_content()
        scraper._crawl_links(max_pages=args.max_pages)
        results = scraper._compile_results()

    elif args.api:
        # Direct API fetch
        result = scraper.scrape_url(args.url, method=args.method, body=args.body)
        results = result

    elif any([args.html, args.css, args.js, args.forms, args.media, args.metadata, args.all, args.headers]):
        # Specific content extraction
        if args.render:
            html = scraper._get_rendered_html()
        else:
            try:
                resp = scraper.session.get(args.url, timeout=scraper.timeout)
                html = resp.text
                if args.headers:
                    scraper.html_data.append({"type": "response_headers", "headers": dict(resp.headers)})
            except Exception as e:
                print(f"[ERROR] {e}")
                sys.exit(1)

        soup = BeautifulSoup(html, "html.parser")

        if args.html or args.all:
            scraper._extract_html_content(soup)
        if args.css or args.all:
            scraper._extract_css(soup)
        if args.js or args.all:
            scraper._extract_js(soup)
        if args.forms or args.all:
            scraper._extract_forms(soup)
        if args.media or args.all:
            scraper._extract_media(soup)
        if args.metadata or args.all:
            scraper._extract_metadata(soup)

        results = scraper._compile_results()

    else:
        # Default: auto mode
        results = scraper.auto_scan(max_pages=args.max_pages)

    # Output
    if not results:
        print("[INFO] No data scraped.")
        sys.exit(0)

    # Print summary
    if isinstance(results, dict) and "summary" in results:
        print(f"\n{'='*70}")
        print("  SCAN SUMMARY")
        print(f"{'='*70}")
        for key, val in results["summary"].items():
            print(f"  {key.replace('_', ' ').title()}: {val}")

    # Save
    output_file = args.output
    fmt = args.format

    if fmt in ("json", "both"):
        json_file = output_file if output_file.endswith(".json") else output_file.rsplit(".", 1)[0] + ".json"
        save_json(results, json_file)

    if fmt in ("csv", "both"):
        csv_file = output_file.rsplit(".", 1)[0] + ".csv" if "." in output_file else output_file + ".csv"
        save_csv(results, csv_file)


if __name__ == "__main__":
    main()
