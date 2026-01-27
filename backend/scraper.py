import requests
from bs4 import BeautifulSoup

def scrape_wikipedia(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (WikiQuizBot/1.0)"
    }

    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code != 200:
        raise Exception("Failed to fetch Wikipedia page")

    soup = BeautifulSoup(response.text, "html.parser")

    title_tag = soup.find("h1")
    title = title_tag.text.strip() if title_tag else "No title found"

    paragraphs = soup.select("p")
    summary = ""
    for p in paragraphs:
        if p.text.strip():
            summary = p.text.strip()
            break

    sections = [
        span.text.strip()
        for span in soup.select("h2 span.mw-headline")
    ]

    full_text = " ".join(p.text.strip() for p in paragraphs if p.text.strip())

    return {
        "title": title,
        "summary": summary,
        "sections": sections,
        "full_text": full_text,
        "raw_html": response.text
    }
