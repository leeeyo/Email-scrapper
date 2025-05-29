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

class GoogleScraper:
    def __init__(self):
        self.results = set()
        self.max_pages = 3
        self.max_retries = 3
        self.delay_range = (2, 4)  # seconds between requests
        
        # Ensure output directory exists
        self.output_dir = "pre-validated_lists"
        os.makedirs(self.output_dir, exist_ok=True)
        
    async def init_browser(self):
        """Initialize browser with anti-detection measures"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,  # Changed to False to see what's happening
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-web-security',
                '--disable-features=IsolateOrigins',
                '--disable-site-isolation-trials',
                '--no-sandbox',
                '--disable-setuid-sandbox'
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
            },
            {
                'name': '1P_JAR',
                'value': datetime.now().strftime("%Y-%m-%d"),
                'domain': '.google.com',
                'path': '/'
            }
        ])
        
        self.page = await self.context.new_page()
        
        # Add random mouse movements and scrolling
        await self.page.evaluate("""() => {
            window.addEventListener('load', () => {
                setInterval(() => {
                    window.scrollBy(0, Math.random() * 100);
                }, 1000);
            });
        }""")

    async def extract_emails_from_page(self, page):
        """Extract emails from the current page content"""
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

    async def handle_captcha(self, page):
        """Handle Google's CAPTCHA if it appears"""
        try:
            captcha = await page.query_selector('form#captcha-form')
            if captcha:
                logger.warning("CAPTCHA detected! Waiting for manual intervention...")
                # Wait for manual intervention
                await page.wait_for_selector('form#captcha-form', state='hidden', timeout=300000)
                return True
        except Exception as e:
            logger.error(f"Error handling CAPTCHA: {str(e)}")
        return False

    async def process_search_results(self, page, query, page_num):
        """Process Google search results page"""
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.google.com/search?q={encoded_query}&start={page_num * 10}"
            logger.info(f"Processing Google search - Page {page_num + 1}")
            
            # Navigate to the search page
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(random.randint(2000, 4000))
            
            # Check for CAPTCHA
            if await self.handle_captcha(page):
                logger.info("CAPTCHA solved, continuing...")
            
            # Wait for search results to load
            await page.wait_for_selector('div#search', timeout=10000)
            
            # Extract search result links using multiple selectors
            links = await page.evaluate("""() => {
                const selectors = [
                    'div.g a[href^="http"]',
                    'div.yuRUbf > a',
                    'div.tF2Cxc > a',
                    'div[data-hveid] a[href^="http"]',
                    'div.rc a[href^="http"]'
                ];
                
                let links = new Set();
                
                for (const selector of selectors) {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        if (el.href && !el.href.includes('google.com')) {
                            links.add(el.href);
                        }
                    });
                }
                
                return Array.from(links);
            }""")
            
            logger.info(f"Found {len(links)} links on Google page {page_num + 1}")
            
            # Process links
            emails = set()
            for link in links[:20]:  # Limit to 20 links per page
                try:
                    await page.goto(link, wait_until="networkidle")
                    await page.wait_for_timeout(random.randint(2000, 4000))
                    
                    # Random scrolling
                    await page.evaluate("""() => {
                        window.scrollTo(0, Math.random() * document.body.scrollHeight);
                    }""")
                    
                    page_emails = await self.extract_emails_from_page(page)
                    emails.update(page_emails)
                except Exception as e:
                    logger.error(f"Error processing link {link}: {str(e)}")
                    continue
            
            return emails
        
        except Exception as e:
            logger.error(f"Error processing Google search results: {str(e)}")
            return set()

    async def scrape_emails(self, query: str):
        """Main scraping function"""
        logger.info(f"Starting email scraping for query: {query}")
        
        try:
            await self.init_browser()
            
            # Process search results
            for i in range(self.max_pages):
                page_emails = await self.process_search_results(self.page, query, i)
                self.results.update(page_emails)
                logger.info(f"Found {len(self.results)} unique emails so far...")
                await asyncio.sleep(random.uniform(*self.delay_range))
            
            # Save results
            if self.results:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join(self.output_dir, f"emails_google_{timestamp}.txt")
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"Email Scraping Results (Google)\n")
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
    scraper = GoogleScraper()
    await scraper.scrape_emails(query)

if __name__ == "__main__":
    asyncio.run(main()) 