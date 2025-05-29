import dns.resolver
import socket
import aiohttp
import asyncio
import logging
from urllib.parse import urlparse
import ssl
import OpenSSL
from datetime import datetime
import argparse
import os
import glob

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DomainValidator:
    def __init__(self):
        self.disposable_domains = set()  # You can load this from a file
        self.news_domains = {
            'gulfnews.com', 'khaleejtimes.com', 'thenational.ae', 
            'emirates247.com', 'arabianbusiness.com'
        }
        self.system_domains = {
            'sentry.io', 'green-acres.com', 'iproperty.com.my'
        }
        
        # Ensure output directory exists
        self.output_dir = "valid_lists"
        self.input_dir = "pre-validated_lists"
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.input_dir, exist_ok=True)
        
    async def is_domain_active(self, domain: str) -> bool:
        """Check if a domain is active by performing DNS and HTTP checks"""
        try:
            # Remove any protocol and path
            domain = domain.lower().strip()
            if '://' in domain:
                domain = urlparse(domain).netloc
            if '/' in domain:
                domain = domain.split('/')[0]
            
            # Check if it's a disposable or system domain
            if domain in self.disposable_domains or domain in self.system_domains:
                return False
                
            # Check DNS records
            try:
                # Check MX records
                mx_records = dns.resolver.resolve(domain, 'MX')
                if not mx_records:
                    logger.warning(f"No MX records found for {domain}")
                    return False
                    
                # Check A records
                a_records = dns.resolver.resolve(domain, 'A')
                if not a_records:
                    logger.warning(f"No A records found for {domain}")
                    return False
                    
            except dns.resolver.NXDOMAIN:
                logger.warning(f"Domain {domain} does not exist")
                return False
            except dns.resolver.NoAnswer:
                logger.warning(f"No DNS records found for {domain}")
                return False
            except Exception as e:
                logger.error(f"DNS check error for {domain}: {str(e)}")
                return False
            
            # Check if website is accessible
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f'https://{domain}', timeout=10) as response:
                        if response.status < 400:  # 2xx and 3xx status codes are good
                            return True
                        logger.warning(f"Website {domain} returned status {response.status}")
                        return False
            except Exception as e:
                logger.error(f"HTTP check error for {domain}: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking domain {domain}: {str(e)}")
            return False
            
    async def is_valid_business_email(self, email: str) -> bool:
        """Check if an email is likely to be a valid business email"""
        try:
            # Basic email format check
            if not '@' in email or not '.' in email:
                return False
                
            # Split email into local part and domain
            local_part, domain = email.lower().split('@')
            
            # Check for common disposable email patterns
            if any(pattern in local_part for pattern in ['temp', 'test', 'demo', 'example']):
                return False
                
            # Check for common business email patterns
            business_patterns = ['info', 'contact', 'sales', 'support', 'admin', 'office', 'enquiry']
            if any(pattern in local_part for pattern in business_patterns):
                return True
                
            # Check if domain is active
            if not await self.is_domain_active(domain):
                return False
                
            # Check SSL certificate
            try:
                cert = ssl.get_server_certificate((domain, 443))
                x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
                expiry_date = datetime.strptime(x509.get_notAfter().decode('ascii'), '%Y%m%d%H%M%SZ')
                if expiry_date < datetime.now():
                    logger.warning(f"SSL certificate expired for {domain}")
                    return False
            except Exception as e:
                logger.error(f"SSL check error for {domain}: {str(e)}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error validating email {email}: {str(e)}")
            return False
            
    async def validate_emails(self, emails: set) -> set:
        """Validate a set of emails and return only valid business emails"""
        valid_emails = set()
        for email in emails:
            if await self.is_valid_business_email(email):
                valid_emails.add(email)
        return valid_emails

    @staticmethod
    def read_emails_from_file(file_path: str) -> set:
        """Read emails from a text file"""
        emails = set()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    # Extract email from line (handles different formats)
                    email = line.strip()
                    if 'Email:' in line:
                        email = line.split('Email:')[1].strip()
                    if email and '@' in email:
                        emails.add(email)
            return emails
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return set()

    def write_emails_to_file(self, emails: set, output_file: str):
        """Write validated emails to a text file"""
        try:
            # Ensure the output file is in the valid_lists directory
            if not output_file.startswith(self.output_dir):
                output_file = os.path.join(self.output_dir, os.path.basename(output_file))
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"Validated Email Results\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Valid Emails: {len(emails)}\n")
                f.write("=" * 50 + "\n\n")
                
                for email in sorted(emails):
                    f.write(f"Email: {email}\n")
                    f.write("-" * 30 + "\n")
            
            logger.info(f"Validated emails saved to {output_file}")
        except Exception as e:
            logger.error(f"Error writing to file {output_file}: {str(e)}")

    async def process_file(self, input_file: str):
        """Process a single file from pre-validated_lists directory"""
        try:
            # Generate output filename
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            output_file = os.path.join(self.output_dir, f"{base_name}_validated.txt")

            # Read emails from file
            emails = self.read_emails_from_file(input_file)
            logger.info(f"Read {len(emails)} emails from {input_file}")

            # Validate emails
            valid_emails = await self.validate_emails(emails)
            logger.info(f"Found {len(valid_emails)} valid emails out of {len(emails)} total emails")

            # Write results to file
            self.write_emails_to_file(valid_emails, output_file)

            # Delete the processed file
            os.remove(input_file)
            logger.info(f"Deleted processed file: {input_file}")

            return True
        except Exception as e:
            logger.error(f"Error processing file {input_file}: {str(e)}")
            return False

    async def process_all_files(self):
        """Process all files in the pre-validated_lists directory"""
        # Get all .txt files in the input directory
        input_files = glob.glob(os.path.join(self.input_dir, "*.txt"))
        
        if not input_files:
            logger.info("No files found in pre-validated_lists directory")
            return

        logger.info(f"Found {len(input_files)} files to process")
        
        # Process each file
        for input_file in input_files:
            logger.info(f"Processing file: {input_file}")
            await self.process_file(input_file)

async def main():
    parser = argparse.ArgumentParser(description='Validate emails from pre-validated_lists directory')
    parser.add_argument('--single-file', help='Process a single file instead of all files in directory')
    
    args = parser.parse_args()
    
    validator = DomainValidator()
    
    if args.single_file:
        # Process single file
        if not os.path.exists(args.single_file):
            logger.error(f"File {args.single_file} does not exist")
            return
        await validator.process_file(args.single_file)
    else:
        # Process all files in directory
        await validator.process_all_files()

if __name__ == "__main__":
    asyncio.run(main()) 