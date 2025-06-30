import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
import random
import time
import logging
import subprocess
import re
from typing import Optional, Dict, Union
from datetime import datetime, timedelta
from flask import current_app
from models import Campaign, CampaignAccount, Lead, Message, db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OdnoklassnikiBot:
    BASE_URL = "https://ok.ru"
    LOGIN_URL = "https://ok.ru"
    
    def __init__(self, proxy_config: Optional[Dict[str, Union[str, int]]] = None):
        self.proxy_config = proxy_config
        self.driver = None
        
    def get_chrome_version(self):
        """Get the installed Chrome version"""
        try:
            # Try PowerShell command first
            process = subprocess.Popen(
                ['powershell', '-command', '(Get-Item "C:\Program Files\Google\Chrome\Application\chrome.exe").VersionInfo.FileVersion'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()
            if stdout:
                version = stdout.strip().split('.')[0]  # Get major version number
                logger.info(f"Detected Chrome version: {version}")
                return int(version)
        except Exception as e:
            logger.warning(f"Could not detect Chrome version using PowerShell: {e}")
            
        try:
            # Try using undetected-chromedriver's built-in version detection
            version = uc.find_chrome_executable()
            if version:
                logger.info(f"Detected Chrome version using undetected-chromedriver: {version}")
                return version
        except Exception as e:
            logger.warning(f"Could not detect Chrome version using undetected-chromedriver: {e}")
        
        # Default to latest known working version
        default_version = 122
        logger.warning(f"Could not detect Chrome version, using default: {default_version}")
        return default_version
        
    def setup_driver(self):
        """Initialize undetected-chromedriver"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info("Starting Chrome driver setup...")
                # Create Chrome options
                options = uc.ChromeOptions()
                
                # Basic options
                options.add_argument("--start-maximized")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--no-sandbox")
                options.add_argument("--lang=en-US")
                options.add_argument("--remote-debugging-port=0")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-software-rasterizer")
                
                # Add random user agent
                user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 OPR/123.0.0.0"
                ]
                options.add_argument(f'--user-agent={random.choice(user_agents)}')
                
                # Add proxy if configured
                if self.proxy_config:
                    # Format proxy string based on type
                    proxy_type = self.proxy_config['type'].lower()
                    host = self.proxy_config['host']
                    port = self.proxy_config['port']
                    username = self.proxy_config.get('username')
                    password = self.proxy_config.get('password')
                    
                    # Build proxy string
                    if username and password:
                        proxy_str = f"{proxy_type}://{username}:{password}@{host}:{port}"
                    else:
                        proxy_str = f"{proxy_type}://{host}:{port}"
                    
                    # Add proxy arguments
                    options.add_argument(f'--proxy-server={proxy_str}')
                    
                    # Additional proxy settings
                    options.add_argument('--proxy-bypass-list=<-loopback>')
                    options.add_argument('--host-resolver-rules="MAP * ~NOTFOUND , EXCLUDE localhost"')
                    
                    # Handle SSL certificates
                    options.add_argument('--ignore-certificate-errors')
                    options.add_argument('--ignore-ssl-errors')
                    
                    # Log proxy configuration (without credentials)
                    logger.info(f"Added proxy configuration: {proxy_type}://{host}:{port}")

                # Additional Chrome options for stability
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--disable-software-rasterizer')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-notifications')
                options.add_argument('--disable-popup-blocking')
                options.add_argument('--disable-web-security')
                options.add_argument('--dns-prefetch-disable')
                
                # Get Chrome version
                chrome_version = self.get_chrome_version()
                logger.info(f"Using Chrome version: {chrome_version}")

                # Clean up any existing Chrome driver processes
                try:
                    import psutil
                    for proc in psutil.process_iter(['name']):
                        if 'chromedriver' in proc.info['name'].lower():
                            proc.kill()
                    logger.info("Cleaned up existing Chrome driver processes")
                except Exception as e:
                    logger.warning(f"Failed to clean up Chrome driver processes: {e}")

                # Initialize Chrome driver with detected version
                self.driver = uc.Chrome(
                    options=options,
                    version_main=chrome_version,
                    use_subprocess=True,
                    driver_executable_path=None,
                    browser_executable_path=None,
                    headless=False,
                    log_level=3,  # Reduce logging noise
                    patcher_force_close=True
                )
                
                # Set page load timeout
                self.driver.set_page_load_timeout(30)
                
                # Set window size
                self.driver.set_window_size(1920, 1080)
                
                # Execute CDP commands to prevent detection
                self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['en-US', 'en']
                        });
                        window.chrome = {
                            runtime: {}
                        };
                    """
                })
                
                # Wait for network to be idle
                time.sleep(2)
                
                logger.info("Chrome driver initialized successfully")
                return True
                
            except Exception as e:
                logger.error(f"Failed to initialize Chrome driver (attempt {retry_count + 1}/{max_retries}): {str(e)}")
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                self.driver = None
                
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(5)  # Wait before retrying
                else:
                    raise Exception(f"Failed to initialize Chrome driver after {max_retries} attempts: {str(e)}")
                    
    def __enter__(self):
        """Context manager entry"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.setup_driver()
                return self
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    logger.warning(f"Retrying setup (attempt {retry_count + 1}/{max_retries})")
                    time.sleep(5)
                else:
                    logger.error(f"Failed to setup driver after {max_retries} attempts")
                    raise
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
                
    def login(self, username: str, password: str) -> bool:
        """Login to Odnoklassniki"""
        try:
            logger.info("Navigating to login page...")
            self.driver.get(self.LOGIN_URL)
            time.sleep(random.uniform(2, 4))
            
            # Wait for login form to be visible
            wait = WebDriverWait(self.driver, 20)
            
            # Try to find the username field with different selectors
            username_field = None
            for selector in [
                (By.NAME, "st.email"),
                (By.ID, "field_email"),
                (By.CSS_SELECTOR, "input[data-l='t,email']"),
                (By.CSS_SELECTOR, "input.form-text[type='text']")
            ]:
                try:
                    username_field = wait.until(EC.presence_of_element_located(selector))
                    if username_field.is_displayed():
                        break
                except:
                    continue
            
            if not username_field:
                logger.error("Could not find username field")
                return False
            
            # Clear and fill username
            username_field.clear()
            self._type_like_human(username_field, username)
            time.sleep(random.uniform(1, 2))
            
            # Try to find the password field with different selectors
            password_field = None
            for selector in [
                (By.NAME, "st.password"),
                (By.ID, "field_password"),
                (By.CSS_SELECTOR, "input[data-l='t,password']"),
                (By.CSS_SELECTOR, "input[type='password']")
            ]:
                try:
                    password_field = wait.until(EC.presence_of_element_located(selector))
                    if password_field.is_displayed():
                        break
                except:
                    continue
            
            if not password_field:
                logger.error("Could not find password field")
                return False
            
            # Clear and fill password
            password_field.clear()
            self._type_like_human(password_field, password)
            time.sleep(random.uniform(1, 2))
            
            # Try to find and click the login button
            login_button = None
            for selector in [
                (By.CSS_SELECTOR, "input[data-l='t,sign_in']"),
                (By.CSS_SELECTOR, "input.button-pro"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//input[@value='Log in']"),
                (By.XPATH, "//div[contains(@class, 'login-form-actions')]//input")
            ]:
                try:
                    login_button = wait.until(EC.element_to_be_clickable(selector))
                    if login_button.is_displayed():
                        break
                except:
                    continue
            
            if not login_button:
                logger.error("Could not find login button")
                return False
            
            # Click login button
            login_button.click()
            time.sleep(random.uniform(3, 5))
            
            # Check if login was successful by looking for common elements on the logged-in page
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-l='t,userPage']")))
                logger.info("Login successful")
                return True
            except:
                logger.error("Login failed - could not verify successful login")
                return False
                
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False
            
    def get_messages(self):
        """Get messages from inbox"""
        try:
            logger.info("Navigating to messages page...")
            self.driver.get(f"{self.BASE_URL}/messages")
            time.sleep(random.uniform(2, 4))
            
            # Wait for messages container
            wait = WebDriverWait(self.driver, 20)
            messages_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-l='t,msgBody']")))
            
            # Find all message elements
            message_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.msg-message")
            
            messages = []
            for element in message_elements:
                try:
                    # Get sender info
                    sender_element = element.find_element(By.CSS_SELECTOR, "a.user-link")
                    sender_id = sender_element.get_attribute("href").split("/")[-1]
                    sender_name = sender_element.text
                    
                    # Get message text
                    text_element = element.find_element(By.CSS_SELECTOR, "div.msg-message_body")
                    message_text = text_element.text
                    
                    # Get message time
                    time_element = element.find_element(By.CSS_SELECTOR, "time.msg-message_time")
                    message_time = self._parse_message_time(time_element.get_attribute("title"))
                    
                    # Get message ID
                    message_id = element.get_attribute("data-msg-id")
                    
                    messages.append({
                        'id': message_id,
                        'sender_id': sender_id,
                        'sender_name': sender_name,
                        'text': message_text,
                        'time': message_time
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse message: {str(e)}")
                    continue
            
            logger.info(f"Found {len(messages)} messages")
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get messages: {str(e)}")
            return []
            
    def _parse_message_time(self, time_str):
        """Parse message time string into datetime object"""
        try:
            # Example: "29 June 2025 18:01"
            return datetime.strptime(time_str, "%d %B %Y %H:%M").strftime("%Y-%m-%d %H:%M:%S")
        except:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
    def _type_like_human(self, element, text: str):
        """Type text like a human would"""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.1, 0.3))  # Random delay between keystrokes

    def send_message(self, identifier: str, message: str, min_delay: int = None, max_delay: int = None) -> bool:
        """Send a message to a profile"""
        try:
            # Navigate to profile
            if not self.find_profile(identifier):
                return False
            
            # Find and click Write button
            write_button = None
            write_button_selectors = [
                "//li[contains(@class, 'u-menu_li') and @data-l='outlandertarget,sendMessage']//a[contains(@href, '/messages/')]",
                "//li[contains(@class, '__custom')]//a[contains(@href, '/messages/')]"
            ]
            
            for selector in write_button_selectors:
                try:
                    write_button = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    if write_button and write_button.is_displayed():
                        break
                except:
                    continue
            
            if not write_button:
                return False
            
            # Click the Write button
            write_button.click()
            
            # Find message input and send message
            try:
                # Try multiple selectors for the message input
                message_input = None
                message_input_selectors = [
                    "//msg-input[@data-tsid='write_msg_input']//div[@contenteditable='true']",
                    "//div[@data-tsid='write_msg_input-input']",
                    "//div[contains(@class, 'js-lottie-observer')][@contenteditable='true']",
                    "//msg-input//div[@contenteditable='true']"
                ]
                
                for selector in message_input_selectors:
                    try:
                        message_input = WebDriverWait(self.driver, 2).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        if message_input and message_input.is_displayed():
                            break
                    except:
                        continue
                
                if not message_input:
                    return False
                
                # Clear existing content
                message_input.clear()
                
                # Type message character by character with small random delays
                for char in message:
                    message_input.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.1))
                
                # Find and click send button
                send_button = None
                send_button_selectors = [
                    "//button[@data-tsid='button_send'][@class='primary-okmsg']",  # Exact match
                    "//button[@data-l='t,sendButton']",  # Data attribute match
                    "//button[contains(@class, 'primary-okmsg')]",  # Class match
                    "//button[@title='Send']"  # Title match
                ]
                
                for selector in send_button_selectors:
                    try:
                        send_button = WebDriverWait(self.driver, 2).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        if send_button and send_button.is_displayed():
                            break
                    except:
                        continue
                
                if not send_button:
                    return False
                
                # Click the send button
                send_button.click()
                
                # Apply campaign delay if specified
                if min_delay and max_delay:
                    delay = random.uniform(min_delay, max_delay)
                    time.sleep(delay)
                
                return True
            except:
                return False
            
        except Exception as e:
            logger.error(f"Error sending message to {identifier}: {str(e)}")
            return False
            
    def find_profile(self, identifier: str) -> bool:
        """Find a profile by URL or username"""
        try:
            # Clean up the identifier and navigate directly
            identifier = identifier.strip()
            
            # Remove @ prefix if present
            if identifier.startswith('@'):
                identifier = identifier.lstrip('@')
            
            # Remove http/https if present
            identifier = identifier.replace('http://', '').replace('https://', '')
            
            # Handle different formats
            if 'ok.ru/profile/' in identifier:
                # Full profile URL format
                profile_id = identifier.split('ok.ru/profile/')[-1].split('/')[0]
                self.driver.get(f"https://ok.ru/profile/{profile_id}")
                return True
            elif identifier.isdigit():
                # Profile ID format
                self.driver.get(f"https://ok.ru/profile/{identifier}")
                return True
            else:
                # Username format
                self.driver.get(f"https://ok.ru/{identifier}")
                return True
                
        except Exception as e:
            logger.error(f"Error finding profile {identifier}: {str(e)}")
            return False 

class CampaignRunner:
    def __init__(self, campaign_id, socketio, app):
        self.campaign_id = campaign_id
        self.socketio = socketio
        self.app = app
        self.running = True
        
    def emit_progress(self, message, status='info'):
        """Emit progress update via Socket.IO"""
        self.socketio.emit('campaign_progress', {
            'campaign_id': self.campaign_id,
            'message': message,
            'status': status,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    def run(self):
        """Main campaign execution loop"""
        with self.app.app_context():
            try:
                campaign = Campaign.query.get(self.campaign_id)
                if not campaign:
                    logger.error(f"Campaign {self.campaign_id} not found")
                    return
                
                # Update campaign status
                campaign.status = 'running'
                db.session.commit()
                
                self.emit_progress("Campaign started", "success")
                
                # Get campaign accounts and their leads
                campaign_accounts = CampaignAccount.query.filter_by(campaign_id=self.campaign_id).all()
                
                for ca in campaign_accounts:
                    if not self.running:
                        break
                        
                    account = ca.account
                    leads = Lead.query.filter_by(campaign_account_id=ca.id).all()
                    
                    self.emit_progress(f"Processing account: {account.login}")
                    
                    for lead in leads:
                        if not self.running:
                            break
                            
                        try:
                            # Simulate sending message (replace with actual OK.ru automation)
                            time.sleep(2)  # Delay between messages
                            
                            # Record the message
                            message = Message(
                                campaign_account_id=ca.id,
                                lead_id=lead.id,
                                content=campaign.message_template,
                                status='sent',
                                sent_at=datetime.now()
                            )
                            db.session.add(message)
                            
                            # Update counters
                            ca.messages_sent += 1
                            lead.status = 'messaged'
                            
                            db.session.commit()
                            
                            self.emit_progress(f"Message sent to {lead.username}", "success")
                            
                        except Exception as e:
                            logger.error(f"Error sending message to {lead.username}: {str(e)}")
                            self.emit_progress(f"Failed to send message to {lead.username}: {str(e)}", "danger")
                            
                            # Record the failed message
                            message = Message(
                                campaign_account_id=ca.id,
                                lead_id=lead.id,
                                content=campaign.message_template,
                                status='failed',
                                error=str(e)
                            )
                            db.session.add(message)
                            db.session.commit()
                
                # Update campaign status when finished
                campaign.status = 'completed' if self.running else 'stopped'
                db.session.commit()
                
                status = "success" if campaign.status == 'completed' else "warning"
                self.emit_progress(f"Campaign {campaign.status}", status)
                
            except Exception as e:
                logger.error(f"Campaign error: {str(e)}")
                self.emit_progress(f"Campaign error: {str(e)}", "danger")
                
                # Update campaign status on error
                campaign = Campaign.query.get(self.campaign_id)
                if campaign:
                    campaign.status = 'error'
                    db.session.commit() 