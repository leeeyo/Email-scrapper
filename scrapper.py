import httpx, re, asyncio, urllib.parse
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import random
from datetime import datetime
import aiohttp
import json
from fake_useragent import UserAgent

EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

PROXY_LIST = [
    # HTTPS proxies from spys.one
    "https://95.143.191.163:8080",  # Russia (Moscow) - Anonymous
    "https://103.14.33.82:8080",    # Singapore - High Anonymous
    "https://43.134.1.77:8080",     # Singapore - High Anonymous
    "https://34.21.79.122:8080",    # United States (Washington) - Anonymous
    "https://34.80.152.137:8080",   # Taiwan (Taipei) - Anonymous
    "https://152.26.229.52:8080",   # United States (Charlotte) - Anonymous
    "https://103.73.193.130:8080",  # Indonesia - Anonymous
    "https://102.223.27.226:8080",  # Equatorial Guinea - High Anonymous
    # Keep some of the original proxies as backup
    "http://2.49.191.123:8080",
    "https://86.98.222.224:8080",
    "http://185.100.84.174:8080",
    "http://212.23.217.71:8080",
    "https://139.185.42.86:3128"
    # Add more proxies here
]

def get_random_proxy():
    return random.choice(PROXY_LIST) if PROXY_LIST else None

def get_random_headers():
    ua = UserAgent()
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
        "DNT": "1"
    }

# Common business directories and contact pages
BUSINESS_DIRECTORIES = [
    "yellowpages.com",
    "yell.com",
    "thomsonlocal.com",
    "hotfrog.com",
    "manta.com",
    "bizapedia.com",
    "linkedin.com/company",
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "contact",
    "about",
    "team",
    "staff",
    "people"
]

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def format_search_query(query):
    # Add various email-related terms to improve results
    email_terms = [
        "contact email",
        "email address",
        "contact us",
        "get in touch",
        "reach us",
        "contact information",
        "email us",
        "contact details",
        "business email",
        "office email"
    ]
    return [f"{query} {term}" for term in email_terms]

# List of search engines to use with their specific parameters
search_engines = {
    "Bing": {
        "url": "https://www.bing.com/search?q={}&first={}",
        "delay": (5, 8),
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "DNT": "1"
        }
    },
    "Google": {
        "url": "https://www.google.com/search?q={}&start={}",
        "delay": (8, 12),
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "DNT": "1"
        }
    },
    "Yahoo": {
        "url": "https://search.yahoo.com/search?p={}&b={}",
        "delay": (4, 6),
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "DNT": "1"
        }
    },
    "DuckDuckGo": {
        "url": "https://duckduckgo.com/html/?q={}&s={}",
        "delay": (3, 5),
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "DNT": "1"
        }
    }
}

async def fetch_page(client, url, search_engine):
    try:
        # Add random delay between requests
        await asyncio.sleep(random.uniform(*search_engines[search_engine]["delay"]))
        
        # Use different headers for each request
        headers = search_engines[search_engine]["headers"].copy()
        headers["User-Agent"] = UserAgent().random
        
        # Add referrer for more realistic behavior
        if "google" in search_engine.lower():
            headers["Referer"] = "https://www.google.com/"
        elif "bing" in search_engine.lower():
            headers["Referer"] = "https://www.bing.com/"
        elif "yahoo" in search_engine.lower():
            headers["Referer"] = "https://search.yahoo.com/"
        elif "duckduckgo" in search_engine.lower():
            headers["Referer"] = "https://duckduckgo.com/"
        
        # Try with proxy first
        proxy = get_random_proxy()
        if proxy:
            try:
                print(f"[*] Trying proxy: {proxy}")
                # Configure proxy for this request
                client.proxies = {
                    "http://": proxy if proxy.startswith("http://") else None,
                    "https://": proxy if proxy.startswith("https://") else None
                }
                # Remove None values
                client.proxies = {k: v for k, v in client.proxies.items() if v is not None}
                
                response = await client.get(url, headers=headers, timeout=30)
                
                # Check if we're being blocked
                if response.status_code == 429 or "captcha" in response.text.lower():
                    print(f"[-] Rate limited or captcha detected on {search_engine}")
                    # Clear proxy and try direct connection
                    client.proxies = None
                    return None
                    
                return response.text
            except Exception as e:
                print(f"[-] Proxy {proxy} failed: {str(e)}")
                client.proxies = None
        
        # If proxy fails or no proxy available, try direct connection
        print("[*] Trying direct connection")
        response = await client.get(url, headers=headers, timeout=30)
        
        # Check if we're being blocked
        if response.status_code == 429 or "captcha" in response.text.lower():
            print(f"[-] Rate limited or captcha detected on {search_engine}")
            return None
            
        return response.text
    except Exception as e:
        print(f"[-] Error fetching {url}: {str(e)}")
        return None

async def extract_emails_from_page(client, url, search_engine):
    try:
        content = await fetch_page(client, url, search_engine)
        if not content:
            return set()
        
        emails = set()
        found_emails = re.findall(EMAIL_REGEX, content)
        
        for email in found_emails:
            email = email.lower()
            if not email.endswith(('.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp')):
                emails.add(email)
                print(f"[+] Found email: {email}")
                print(f"    Source: {url}")
                print(f"    Search Engine: {search_engine}")
                print(f"    Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("    " + "-" * 50)
        
        return emails
    except Exception as e:
        print(f"[-] Error processing {url}: {str(e)}")
        return set()

async def process_search_results(client, search_url, page_num, search_engine):
    try:
        url = search_url.format(page_num * 10)
        print(f"\n[*] Searching on {search_engine} - Page {page_num + 1}")
        content = await fetch_page(client, url, search_engine)
        if not content:
            return set()
        
        soup = BeautifulSoup(content, "html.parser")
        links = set()
        
        # Extract all links
        for a in soup.find_all("a", href=True):
            href = a['href']
            if href.startswith("http") and is_valid_url(href):
                links.add(href)
        
        # Prioritize business directory and contact pages
        prioritized_links = []
        other_links = []
        
        for link in links:
            if any(dir in link.lower() for dir in BUSINESS_DIRECTORIES):
                prioritized_links.append(link)
            else:
                other_links.append(link)
        
        # Process prioritized links first
        all_links = prioritized_links + other_links
        
        # Process links in parallel
        tasks = []
        for link in all_links[:20]:  # Limit to 20 links per page to avoid overwhelming
            tasks.append(extract_emails_from_page(client, link, search_engine))
            await asyncio.sleep(random.uniform(1, 3))  # Random delay between requests
        
        results = await asyncio.gather(*tasks)
        return set().union(*results)
    
    except Exception as e:
        print(f"[-] Error processing search results: {str(e)}")
        return set()

async def scrape_emails(query: str, max_pages: int = 3):
    results = set()
    formatted_queries = format_search_query(query)
    
    print(f"\n[*] Starting email scraping for query: {query}")
    print(f"[*] Using search engines: {', '.join(search_engines.keys())}")
    print(f"[*] Maximum pages per engine: {max_pages}")
    print("=" * 70)
    
    # Configure httpx client with longer timeout and retries
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        verify=True,
        http2=True
    ) as client:
        for formatted_query in formatted_queries:
            encoded_query = urllib.parse.quote(formatted_query)
            print(f"\n[*] Processing query: {formatted_query}")
            
            for engine_name, engine_config in search_engines.items():
                search_url = engine_config["url"].format(encoded_query, "{}")
                
                # Process pages in parallel
                tasks = []
                for i in range(max_pages):
                    tasks.append(process_search_results(client, search_url, i, engine_name))
                    # Use engine-specific delays
                    await asyncio.sleep(random.uniform(*engine_config["delay"]))
                
                page_results = await asyncio.gather(*tasks)
                for page_emails in page_results:
                    results.update(page_emails)
                
                print(f"[+] Found {len(results)} unique emails so far...")
                
                # Random delay between search engines
                await asyncio.sleep(random.uniform(8, 15))

    print(f"\n[+] Total unique emails found: {len(results)}")

    # Save to text file with detailed information
    if results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"emails_{timestamp}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"Email Scraping Results\n")
            f.write(f"Query: {query}\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Emails Found: {len(results)}\n")
            f.write("=" * 50 + "\n\n")
            
            for email in sorted(results):
                f.write(f"Email: {email}\n")
                f.write("-" * 30 + "\n")
        
        print(f"[✓] Emails saved to {filename}")
    else:
        print("[-] No emails found. Try a different search query.")

# Run it
if __name__ == "__main__":
    query = input("Enter your search query (e.g. dentists in Dubai): ")
    asyncio.run(scrape_emails(query))
