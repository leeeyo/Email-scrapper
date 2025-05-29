import asyncio
from playwright.async_api import async_playwright
import re
from datetime import datetime
import random
import logging
import json
from bs4 import BeautifulSoup
import urllib.parse
import time
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

class BingScraper:
    def __init__(self):
        self.results = set()
        self.max_pages = 3
        self.max_retries = 3
        self.delay_range = (2, 4)  # seconds between requests
        
        # Ensure output directory exists
        self.output_dir = "pre-validated_lists"
        os.makedirs(self.output_dir, exist_ok=True)
        
    async def extract_emails_from_page(self, page, url):
        try:
            # Get page content
            content = await page.content()
            
            # Extract emails
            emails = set()
            found_emails = re.findall(EMAIL_REGEX, content)
            
            for email in found_emails:
                email = email.lower()
                if not email.endswith(('.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp')):
                    emails.add(email)
                    print(f"[+] Found email: {email}")
                    print(f"    Source: {url}")
                    print(f"    Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print("    " + "-" * 50)
            
            return emails
        except Exception as e:
            print(f"[-] Error processing {url}: {str(e)}")
            return set()

    async def process_search_results(self, page, search_url, page_num):
        try:
            # Navigate to search URL
            url = search_url.format(page_num * 10)
            print(f"\n[*] Searching on Bing - Page {page_num + 1}")
            
            # Try to navigate to the page with retries
            for attempt in range(self.max_retries):
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_load_state('networkidle', timeout=30000)
                    break
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        print(f"[-] Failed to load page after {self.max_retries} attempts: {str(e)}")
                        return set()
                    print(f"[*] Retry {attempt + 1}/{self.max_retries} for page {page_num + 1}")
                    await asyncio.sleep(random.uniform(5, 10))
            
            # Wait for search results to load
            try:
                await page.wait_for_selector('ol#b_results', timeout=10000)
            except:
                print(f"[-] No search results found on page {page_num + 1}")
                return set()
            
            # Extract all links
            links = await page.evaluate('''() => {
                const results = document.querySelectorAll('ol#b_results li.b_algo h2 a');
                return Array.from(results).map(a => a.href).filter(href => href.startsWith('http'));
            }''')
            
            # Process each link
            emails = set()
            for link in links[:20]:  # Limit to 20 links per page
                try:
                    # Navigate to the link with retries
                    for attempt in range(self.max_retries):
                        try:
                            await page.goto(link, wait_until='domcontentloaded', timeout=30000)
                            await page.wait_for_load_state('networkidle', timeout=30000)
                            break
                        except Exception as e:
                            if attempt == self.max_retries - 1:
                                print(f"[-] Failed to load {link} after {self.max_retries} attempts")
                                continue
                            await asyncio.sleep(random.uniform(2, 4))
                    
                    # Extract emails
                    page_emails = await self.extract_emails_from_page(page, link)
                    emails.update(page_emails)
                    
                    # Random delay between requests
                    await asyncio.sleep(random.uniform(2, 4))
                    
                except Exception as e:
                    print(f"[-] Error processing {link}: {str(e)}")
                    continue
            
            return emails
        
        except Exception as e:
            print(f"[-] Error processing search results: {str(e)}")
            return set()

    async def scrape_emails(self, query: str):
        """Main scraping function"""
        logger.info(f"Starting email scraping for query: {query}")
        
        try:
            async with async_playwright() as p:
                # Launch browser with additional options
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--disable-site-isolation-trials'
                    ]
                )
                
                # Create context with additional settings
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    java_script_enabled=True,
                    bypass_csp=True
                )
                
                # Create new page
                page = await context.new_page()
                
                try:
                    # Encode the query properly
                    encoded_query = urllib.parse.quote(query)
                    search_url = f"https://www.bing.com/search?q={encoded_query}&first={{}}"
                    
                    # Process pages sequentially to avoid overwhelming
                    for i in range(self.max_pages):
                        page_emails = await self.process_search_results(page, search_url, i)
                        self.results.update(page_emails)
                        logger.info(f"Found {len(self.results)} unique emails so far...")
                        await asyncio.sleep(random.uniform(*self.delay_range))
                    
                    # Save results
                    if self.results:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = os.path.join(self.output_dir, f"emails_bing_{timestamp}.txt")
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write(f"Email Scraping Results (Bing)\n")
                            f.write(f"Query: {query}\n")
                            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            f.write(f"Total Emails Found: {len(self.results)}\n")
                            f.write("=" * 50 + "\n\n")
                            
                            for email in sorted(self.results):
                                f.write(f"Email: {email}\n")
                                f.write("-" * 30 + "\n")
                        
                        logger.info(f"Emails saved to {filename}")
                    else:
                        logger.warning("No emails found. Try a different search query.")
                
                finally:
                    await browser.close()
        
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")

async def main():
    query = input("Enter your search query (e.g. dentists in Dubai): ")
    scraper = BingScraper()
    await scraper.scrape_emails(query)

if __name__ == "__main__":
    asyncio.run(main()) 