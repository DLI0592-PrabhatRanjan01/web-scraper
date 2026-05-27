# Web Scraper

A flexible Python web scraper that lets you extract specific data or entire page content from any website.

## Setup

```bash
cd web-scraper
pip install -r requirements.txt
```

## Usage

### Option 1: Command-Line (Quick & Powerful)

```bash
# Scrape all visible text from a page
python scraper.py https://example.com --all

# Scrape specific elements using CSS selectors
python scraper.py https://quotes.toscrape.com --selectors ".quote .text, .quote .author"

# Scrape all links
python scraper.py https://example.com --links --output links.csv

# Scrape all images
python scraper.py https://example.com --images -o images.json

# Scrape tables (great for Wikipedia, sports stats, etc.)
python scraper.py https://example.com --tables -o tables.csv

# Scrape page metadata (title, description, Open Graph tags)
python scraper.py https://example.com --metadata

# Extract specific attributes from elements
python scraper.py https://example.com --selectors "a.product" --attrs "href,data-price"

# Combine multiple modes
python scraper.py https://example.com --links --images --metadata -o full_data.json
```

### Option 2: Interactive Mode (Guided)

```bash
python interactive.py
```

This will walk you through step-by-step:
1. Enter the URL
2. Choose what to scrape
3. Pick output format

### Option 3: Config File (Repeatable)

Edit `config.json` with your settings:

```json
{
    "url": "https://quotes.toscrape.com",
    "mode": "selectors",
    "selectors": ".quote .text, .quote .author",
    "attrs": null,
    "output": "quotes.json",
    "format": "json"
}
```

Then run:
```bash
python interactive.py --config
```

## Config Options

| Field | Description | Values |
|-------|-------------|--------|
| `url` | Target website URL | Any valid URL |
| `mode` | What to scrape | `all`, `selectors`, `links`, `images`, `tables`, `metadata` |
| `selectors` | CSS selectors | Any valid CSS selector string |
| `attrs` | Attributes to extract | Comma-separated attribute names |
| `output` | Output filename | `.json` or `.csv` extension |

## CSS Selector Cheat Sheet

| Selector | Meaning |
|----------|---------|
| `h1` | All `<h1>` tags |
| `.classname` | Elements with that class |
| `#id` | Element with that ID |
| `div > p` | Direct child `<p>` of `<div>` |
| `a[href]` | Links with href attribute |
| `.card .title` | `.title` inside `.card` |
| `table tr td` | Table cells |

## Output Formats

- **JSON** (default): Structured data, great for further processing
- **CSV**: Spreadsheet-compatible, good for Excel/Google Sheets

## Examples

### Scrape product prices
```bash
python scraper.py https://shop.example.com --selectors ".product-name, .product-price" -o products.csv
```

### Scrape news headlines
```bash
python scraper.py https://news.example.com --selectors "h2.headline, .article-summary" -o news.json
```

### Scrape all external links
```bash
python scraper.py https://example.com --links -o links.json
# Then filter: external links have "is_external": true
```

## Notes

- The scraper respects a 30-second timeout per request
- A browser-like User-Agent header is sent to avoid basic blocks
- For JavaScript-rendered pages (SPAs), this basic scraper won't work — you'd need Selenium or Playwright
- Always check a website's `robots.txt` and Terms of Service before scraping
