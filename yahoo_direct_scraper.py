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

# Direct site URLs with proper formatting
DIRECT_SITES = {
    "yellowpages": "https://www.yellowpages.com/search?search_terms={}",
    "hotfrog": "https://www.hotfrog.com/search?q={}",
    "manta": "https://www.manta.com/search?search={}",
    "facebook": "https://www.facebook.com/pages/search/top?q={}"
}

async def extract_emails_from_page(page):
    try:
        content = await page.content()
        emails = set()
        found_emails = re.findall(EMAIL_REGEX, content)
        
        for email in found_emails:
            email = email.lower()
            if not email.endswith(('.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp')):
                emails.add(email)
                logger.info(f"Found email: {email}")
        
        return emails
    except Exception as e:
        logger.error(f"Error extracting emails: {str(e)}")
        return set()

async def process_yahoo_search(page, query, page_num):
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://search.yahoo.com/search?p={encoded_query}&b={page_num * 10}"
        logger.info(f"Processing Yahoo search - Page {page_num + 1}")
        
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(random.randint(2000, 4000))
        
        # Extract search result links
        links = await page.evaluate("""() => {
            const results = Array.from(document.querySelectorAll('div.algo-sr, div.algo'));
            return results.map(result => {
                const link = result.querySelector('a');
                return link ? link.href : null;
            }).filter(href => href && href.startsWith('http'));
        }""")
        
        logger.info(f"Found {len(links)} links on Yahoo page {page_num + 1}")
        
        # Process links
        emails = set()
        for link in links[:20]:  # Limit to 20 links per page
            try:
                await page.goto(link, wait_until="networkidle")
                await page.wait_for_timeout(random.randint(2000, 4000))
                page_emails = await extract_emails_from_page(page)
                emails.update(page_emails)
            except Exception as e:
                logger.error(f"Error processing link {link}: {str(e)}")
                continue
        
        return emails
    
    except Exception as e:
        logger.error(f"Error processing Yahoo search results: {str(e)}")
        return set()

async def process_direct_site(page, site_name, query):
    try:
        encoded_query = urllib.parse.quote(query)
        url = DIRECT_SITES[site_name].format(encoded_query)
        logger.info(f"Processing {site_name}")
        
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(random.randint(2000, 4000))
        
        # Site-specific link extraction
        links = await page.evaluate("""(siteName) => {
            let selectors = [];
            switch(siteName) {
                case 'yellowpages':
                    selectors = ['div.result a.business-name', 'div.search-results a.business-name'];
                    break;
                case 'hotfrog':
                    selectors = ['div.company-listing a.company-name', 'div.search-result a.company-name'];
                    break;
                case 'manta':
                    selectors = ['div.search-result a.company-name', 'div.company-card a.company-name'];
                    break;
                case 'facebook':
                    selectors = ['div[role="article"] a[href*="/pages/"]', 'div.search-result a[href*="/pages/"]'];
                    break;
            }
            
            let links = [];
            for (const selector of selectors) {
                const elements = document.querySelectorAll(selector);
                elements.forEach(el => {
                    if (el.href) links.push(el.href);
                });
            }
            return links;
        }""", site_name)
        
        logger.info(f"Found {len(links)} links on {site_name}")
        
        # Process links
        emails = set()
        for link in links[:20]:  # Limit to 20 links per page
            try:
                await page.goto(link, wait_until="networkidle")
                await page.wait_for_timeout(random.randint(2000, 4000))
                page_emails = await extract_emails_from_page(page)
                emails.update(page_emails)
            except Exception as e:
                logger.error(f"Error processing link {link}: {str(e)}")
                continue
        
        return emails
    
    except Exception as e:
        logger.error(f"Error processing {site_name}: {str(e)}")
        return set()

class YahooDirectScraper:
    def __init__(self):
        self.results = set()
        self.max_pages = 3
        self.max_retries = 3
        self.delay_range = (2, 4)  # seconds between requests
        
        # Ensure output directory exists
        self.output_dir = "pre-validated_lists"
        os.makedirs(self.output_dir, exist_ok=True)
        
    async def init_browser(self):
        async with async_playwright() as p:
            # Launch browser with realistic settings
            self.browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials'
                ]
            )
            
            # Create a new context with realistic browser settings
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                geolocation={'latitude': 40.7128, 'longitude': -74.0060},
                permissions=['geolocation'],
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'DNT': '1'
                }
            )
            
            # Create a new page
            self.page = await self.context.new_page()
            
            # Add cookies for more realistic behavior
            await self.context.add_cookies([
                {
                    'name': 'CONSENT',
                    'value': 'YES+cb',
                    'domain': '.google.com',
                    'path': '/'
                },
                {
                    'name': 'NID',
                    'value': str(random.randint(1000000000, 9999999999)),
                    'domain': '.google.com',
                    'path': '/'
                }
            ])

    async def scrape_emails(self, query: str):
        """Main scraping function"""
        logger.info(f"Starting email scraping for query: {query}")
        
        try:
            await self.init_browser()
            
            # Process Yahoo search
            for i in range(self.max_pages):
                page_emails = await process_yahoo_search(self.page, query, i)
                self.results.update(page_emails)
                logger.info(f"Found {len(self.results)} unique emails so far...")
                await asyncio.sleep(random.uniform(*self.delay_range))
            
            # Process direct sites
            for site_name in DIRECT_SITES:
                site_emails = await process_direct_site(self.page, site_name, query)
                self.results.update(site_emails)
                logger.info(f"Found {len(self.results)} unique emails so far...")
                await asyncio.sleep(random.uniform(*self.delay_range))
            
            # Save results
            if self.results:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(self.output_dir, f"emails_yahoo_direct_{timestamp}.txt")
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"Email Scraping Results (Yahoo & Direct Sites)\n")
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
        
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
        
        finally:
            if hasattr(self, 'browser'):
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()

async def main():
    query = input("Enter your search query (e.g. dentists in Dubai): ")
    scraper = YahooDirectScraper()
    await scraper.scrape_emails(query)

if __name__ == "__main__":
    asyncio.run(main()) 