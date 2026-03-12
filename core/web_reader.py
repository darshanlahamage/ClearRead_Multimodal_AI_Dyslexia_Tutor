"""
Web Reader — URL Simplification for Dyslexia
----------------------------------------------
Fetches a web page by URL, extracts its text content and images, and uses
Nova 2 Lite to produce a dyslexia-friendly simplified version that preserves
the full content structure, images, and factual details.

Pipeline:
    1. requests.get(url) → raw HTML
    2. BeautifulSoup: extract images (absolute URLs) + strip nav/scripts
    3. Build text + image-placeholder map
    4. Nova 2 Lite (extended thinking) → simplified HTML with image tags
    5. Replace image placeholders with real URLs
"""

import json
import logging
import re
from urllib.parse import urljoin

import boto3
import requests
from bs4 import BeautifulSoup

from config.settings import AWS_REGION, LITE_MODEL_ID

logger = logging.getLogger(__name__)

_bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

# Higher cap to preserve more content
MAX_EXTRACT_CHARS = 12000
MAX_IMAGES = 15


def fetch_and_extract(url: str) -> dict:
    """
    Fetch a URL, extract readable text AND image URLs.

    Returns:
        {title, url, raw_text, word_count, images: [{src, alt, context}]}
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch URL {url}: {e}")
        return {"error": f"Could not fetch the page: {str(e)}"}

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract page title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Extract images BEFORE stripping tags
    images = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src or src.startswith("data:"):
            continue
        # Resolve relative URLs to absolute
        abs_src = urljoin(url, src)
        alt = img.get("alt", "").strip()
        # Get surrounding text for context
        parent = img.find_parent(["p", "div", "figure", "section", "td"])
        context = parent.get_text(strip=True)[:100] if parent else ""
        images.append({"src": abs_src, "alt": alt, "context": context})
        if len(images) >= MAX_IMAGES:
            break

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "form", "iframe", "noscript", "meta", "link", "svg"]):
        tag.decompose()

    # Extract text from remaining content
    text = soup.get_text(separator="\n", strip=True)

    # Clean up: collapse multiple newlines, remove very short lines (nav remnants)
    lines = [line.strip() for line in text.split("\n") if len(line.strip()) > 15]
    clean_text = "\n".join(lines)

    # Truncate if way too long
    if len(clean_text) > MAX_EXTRACT_CHARS:
        clean_text = clean_text[:MAX_EXTRACT_CHARS] + "\n[Content truncated for processing]"

    word_count = len(clean_text.split())

    return {
        "title": title,
        "url": url,
        "raw_text": clean_text,
        "word_count": word_count,
        "images": images,
    }


def simplify_for_dyslexia(extracted: dict, learner_profile: dict = None) -> dict:
    """
    Use Nova 2 Lite to simplify extracted web content for dyslexic readers.
    Preserves full content, structure, and image placements.
    """
    raw_text = extracted.get("raw_text", "")
    title = extracted.get("title", "Unknown Page")
    images = extracted.get("images", [])

    if not raw_text:
        return _fallback_result(extracted)

    # Build image reference list for the prompt
    image_refs = ""
    if images:
        image_refs = "\n\nIMAGES FROM THE ORIGINAL PAGE (use these placeholders in your HTML):\n"
        for i, img in enumerate(images):
            image_refs += f'  {{{{IMG_{i}}}}} — alt: "{img["alt"]}", context: "{img["context"][:60]}"\n'
        image_refs += "\nInsert these image placeholders where they make sense in the content. Use this format: <img src=\"{{IMG_0}}\" alt=\"description\" class=\"wr-img\">\n"

    # Build profile context if available
    profile_context = ""
    if learner_profile:
        phon = learner_profile.get("phonological_decoding", {})
        if isinstance(phon, dict) and phon.get("severity", 0) > 5:
            patterns = phon.get("patterns", [])
            profile_context = f"\nThe reader struggles with these phoneme patterns: {', '.join(patterns)}. Use simpler synonyms where possible."

    prompt = f"""You are a reading accessibility specialist. Transform this web page into a dyslexia-friendly format.

PAGE TITLE: {title}

ORIGINAL CONTENT:
{raw_text}
{image_refs}
{profile_context}

IMPORTANT RULES:
1. PRESERVE ALL CONTENT — do NOT remove or skip any sections. Simplify the language, not the amount.
2. Use proper HTML structure: <h1> for page title, <h2> for main sections, <h3> for subsections.
3. Rewrite complex sentences into clearer, shorter sentences. Do NOT use overly simple baby language — just make it easier to read.
4. Replace jargon with simpler words, but keep technical terms if they are important (add a brief explanation in parentheses).
5. Use <ul>/<li> for lists, <p> for paragraphs.
6. Add paragraph breaks every 2-3 sentences — no walls of text.
7. If image placeholders were provided, include them in appropriate locations using <img src="{{{{IMG_N}}}}" alt="description" class="wr-img">.
8. Wrap key vocabulary in <strong> tags.
9. Use <blockquote> for important definitions or formulas.

OUTPUT FORMAT — return ONLY a valid JSON object:
{{
    "simplified_html": "<h1>Page Title</h1><p>Introduction...</p><h2>Section</h2><p>Content...</p><img src=\\"{{{{IMG_0}}}}\\" alt=\\"...\\" class=\\"wr-img\\"><h2>Another Section</h2><ul><li>Point</li></ul>",
    "summary": "A 3-4 sentence summary of the page for a young reader",
    "key_points": ["Point 1", "Point 2", "Point 3", "Point 4", "Point 5"],
    "vocabulary_words": [
        {{"word": "term", "definition": "simple definition"}},
        {{"word": "term2", "definition": "simple definition"}}
    ],
    "sonic_context": "A detailed 5-6 sentence summary covering ALL the main topics, facts, and concepts on this page. A voice AI tutor will use this to discuss the page with the student and answer questions. Be thorough."
}}"""

    try:
        response = _bedrock.converse(
            modelId=LITE_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            additionalModelRequestFields={
                "thinking": {"type": "enabled", "budget_tokens": 8000}
            },
        )
    except Exception as e:
        logger.error(f"Nova Lite simplification failed: {e}")
        return _fallback_result(extracted)

    # Parse response — handle thinking blocks from extended thinking
    result = None
    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    for block in content_blocks:
        block_type = block.get("type", "")
        if block_type == "thinking":
            continue
        text_content = block.get("text", "")
        if not text_content:
            continue

        cleaned = re.sub(r"```json|```", "", text_content).strip()
        try:
            result = json.loads(cleaned)
            break
        except json.JSONDecodeError:
            # Try extracting JSON from the response
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group())
                    break
                except json.JSONDecodeError:
                    pass

    if not result:
        logger.warning("Failed to parse Nova Lite simplification response")
        return _fallback_result(extracted)

    # Replace image placeholders with actual URLs
    simplified_html = result.get("simplified_html", "")
    for i, img in enumerate(images):
        placeholder = f"{{{{IMG_{i}}}}}"
        simplified_html = simplified_html.replace(placeholder, img["src"])
        # Also handle URL-encoded or escaped versions
        simplified_html = simplified_html.replace(f"{{IMG_{i}}}", img["src"])

    return {
        "title": title,
        "url": extracted.get("url", ""),
        "original_word_count": extracted.get("word_count", 0),
        "simplified_html": simplified_html,
        "summary": result.get("summary", ""),
        "key_points": result.get("key_points", []),
        "vocabulary_words": result.get("vocabulary_words", []),
        "sonic_context": result.get("sonic_context", f"This page is about: {title}"),
        "images": images,
    }


def _fallback_result(extracted: dict) -> dict:
    """Return a basic result when Nova Lite is unavailable."""
    raw = extracted.get("raw_text", "")
    paragraphs = raw.split("\n")
    html_parts = [f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()]
    simple_html = "\n".join(html_parts[:50])

    return {
        "title": extracted.get("title", "Web Page"),
        "url": extracted.get("url", ""),
        "original_word_count": extracted.get("word_count", 0),
        "simplified_html": simple_html,
        "summary": f"This page is about: {extracted.get('title', 'unknown topic')}",
        "key_points": [],
        "vocabulary_words": [],
        "sonic_context": f"The student is reading a web page titled '{extracted.get('title', '')}'. Help them understand the content.",
        "images": extracted.get("images", []),
    }
