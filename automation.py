import undetected_chromedriver as uc
from seleniumwire import webdriver
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
        """Initialize undetected-chromedriver with selenium-wire"""
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
                
                # Selenium Wire options for proxy
                seleniumwire_options = {}
                
                if self.proxy_config:
                    proxy_type = self.proxy_config['type'].lower()
                    host = self.proxy_config['host']
                    port = self.proxy_config['port']
                    username = self.proxy_config.get('username')
                    password = self.proxy_config.get('password')
                    
                    # Format proxy URL with authentication
                    if username and password:
                        proxy_url = f"{proxy_type}://{username}:{password}@{host}:{port}"
                    else:
                        proxy_url = f"{proxy_type}://{host}:{port}"
                    
                    # Configure Selenium Wire proxy
                    seleniumwire_options = {
                        'proxy': {
                            'http': proxy_url,
                            'https': proxy_url
                        },
                        'verify_ssl': False  # Sometimes needed with proxies
                    }
                    
                    logger.info(f"Configured proxy: {proxy_type}://{host}:{port}")
                
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
                
                # Initialize Chrome driver with Selenium Wire
                self.driver = uc.Chrome(
                    options=options,
                    version_main=chrome_version,
                    seleniumwire_options=seleniumwire_options,
                    use_subprocess=True,
                    driver_executable_path=None,
                    browser_executable_path=None,
                    headless=False,
                    log_level=3
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
                
                # Test proxy by loading a test URL
                if self.proxy_config:
                    try:
                        logger.info("Testing proxy connection...")
                        self.driver.get("https://www.google.com")
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.NAME, "q"))
                        )
                        logger.info("Proxy test successful")
                    except Exception as e:
                        logger.error(f"Proxy test failed: {e}")
                        raise Exception("Proxy connection failed")
                
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
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.quit()
        
    def quit(self):
        """Close the browser"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            
    def login(self, username: str, password: str) -> bool:
        """Login to OK.ru account"""
        try:
            logger.info(f"Attempting to login with username: {username}")
            
            # Navigate to login page
            self.driver.get("https://ok.ru")
            time.sleep(random.uniform(2, 3))
            
            # Find and fill username field
            username_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "st.email"))
            )
            username_input.clear()
            time.sleep(random.uniform(0.5, 1))
            self._type_like_human(username_input, username)
            
            # Find and fill password field
            password_input = self.driver.find_element(By.NAME, "st.password")
            password_input.clear()
            time.sleep(random.uniform(0.5, 1))
            self._type_like_human(password_input, password)
            
            # Click login button
            login_button = self.driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
            login_button.click()
            
            # Wait for login to complete and verify
            try:
                # Wait for either success or failure indicators
                WebDriverWait(self.driver, 15).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-l='t,userPage']")),  # Profile page
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.toolbar_nav_i")),  # Nav menu
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.nav-side.__navigation")),  # Side nav
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.feed")),  # Feed page
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-l='t,nav_menu']"))  # Alt nav menu
                    )
                )
                
                # Additional verification - check URL and page content
                current_url = self.driver.current_url
                if "login" in current_url.lower() or "blocked" in current_url.lower():
                    logger.error("Login failed - redirected to login/block page")
                    return False
                    
                # Check for error messages
                error_messages = self.driver.find_elements(By.CSS_SELECTOR, "div.input-e")
                if error_messages:
                    error_text = error_messages[0].text
                    logger.error(f"Login failed - error message: {error_text}")
                    return False
                
                # Additional check - try to find user menu or profile elements
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.any_of(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-l='t,userPage']")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-l='t,nav_menu']")),
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div.nav-side.__navigation"))
                        )
                    )
                except:
                    logger.warning("Could not find user menu elements, but proceeding...")
                
                logger.info("Login successful")
                return True
                
            except TimeoutException:
                logger.error("Login failed - could not verify successful login")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return False
            
    def _type_like_human(self, element, text: str):
        """Type text with random delays between characters"""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.1, 0.3))
            
    def find_profile(self, identifier: str) -> bool:
        """Find a profile by URL"""
        try:
            # Clean up the identifier
            identifier = identifier.strip()
            
            # Remove http/https if present
            identifier = identifier.replace('http://', '').replace('https://', '')
            
            # Extract profile ID from URL
            if 'ok.ru/profile/' in identifier:
                profile_id = identifier.split('ok.ru/profile/')[-1].split('/')[0]
                url = f"https://ok.ru/profile/{profile_id}"
            else:
                # If somehow we got a non-profile URL, try using it directly
                url = f"https://{identifier}"
                
            logger.info(f"Navigating to profile: {url}")
            self.driver.get(url)
            
            # Wait for profile page to load - try multiple selectors
            try:
                # List of selectors that indicate we're on a profile page
                profile_selectors = [
                    "div[data-l='t,userPage']",  # Primary profile indicator
                    "div.profile-user-info",      # Profile info container
                    "div.user-grid",              # User grid layout
                    "div.user-page",              # General profile page container
                    "div[data-module='UserProfile']"  # Profile module
                ]
                
                # Wait for any of these selectors to be present
                for selector in profile_selectors:
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        logger.info(f"Successfully loaded profile: {url}")
                        return True
                    except TimeoutException:
                        continue
                
                # If we get here, none of the selectors were found
                logger.error(f"Could not verify profile page elements: {url}")
                
                # Check if we're on an error page or blocked
                error_selectors = [
                    "div.error-page",
                    "div.access-restricted",
                    "div.user-blocked"
                ]
                
                for error_selector in error_selectors:
                    try:
                        error_element = self.driver.find_element(By.CSS_SELECTOR, error_selector)
                        if error_element.is_displayed():
                            logger.error(f"Found error page ({error_selector}): {url}")
                            return False
                    except NoSuchElementException:
                        continue
                
                # If we're not on an error page, check the URL to verify we at least landed on the profile
                current_url = self.driver.current_url
                if profile_id in current_url:
                    logger.info(f"Profile URL verified but elements not found. Proceeding anyway: {url}")
                    return True
                    
                return False
                
            except Exception as e:
                logger.error(f"Error verifying profile page: {url} - {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error finding profile {identifier}: {str(e)}")
            return False
            
    def send_message(self, identifier: str, message: str, min_delay: int = None, max_delay: int = None) -> bool:
        """Send a message to a profile"""
        try:
            logger.info(f"Attempting to send message to {identifier}")
            
            # Check if we need to navigate to the profile
            current_url = self.driver.current_url
            profile_id = identifier.split('ok.ru/profile/')[-1].split('/')[0] if 'ok.ru/profile/' in identifier else None
            
            if not profile_id or profile_id not in current_url:
                # Only navigate if we're not already on the profile
                if not self.find_profile(identifier):
                    logger.error(f"Could not find profile: {identifier}")
                    return False
            else:
                logger.info("Already on correct profile page")
            
            # Wait for page to load
            time.sleep(random.uniform(2, 4))
            
            # Find and click Write button using multiple selectors
            write_button_selectors = [
                # Exact match selectors
                "//li[@class='u-menu_li __hl __hla __custom' and @data-l='outlandertarget,sendMessage,t,sendMessage']//a[contains(@href, '/messages/')]",
                "//a[contains(@class, 'button-pro') and contains(@hrefattrs, 'st.cmd=userMessageNewPage')]",
                # Broader match selectors
                "//li[contains(@class, 'u-menu_li')]//a[contains(@href, '/messages/')]",
                "//a[contains(@href, '/messages/')]",
                # Additional selectors
                "//div[contains(@class, 'profile-user-info')]//a[contains(@href, '/messages/')]",
                "//a[contains(@class, 'button-pro') and contains(@href, '/messages/')]"
            ]
            
            write_button = None
            for selector in write_button_selectors:
                try:
                    write_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    if write_button and write_button.is_displayed():
                        logger.info(f"Found write button using selector: {selector}")
                        break
                except:
                    continue
            
            if not write_button:
                logger.error(f"Could not find write button for {identifier}")
                return False
            
            # Click the Write button and wait for message page
            write_button.click()
            time.sleep(random.uniform(2, 3))
            
            # Find message input and send message
            try:
                # Try multiple selectors for the message input
                message_input = None
                message_input_selectors = [
                    "//msg-input[@data-tsid='write_msg_input']//div[@contenteditable='true']",
                    "//div[@data-tsid='write_msg_input-input']",
                    "//div[contains(@class, 'js-lottie-observer')][@contenteditable='true']",
                    "//msg-input//div[@contenteditable='true']",
                    "//div[contains(@class, 'input_placeholder')]//div[@contenteditable='true']",
                    # Additional backup selectors
                    "//div[contains(@class, 'message-input')]//div[@contenteditable='true']",
                    "//div[contains(@class, 'composer_input')]//div[@contenteditable='true']"
                ]
                
                for selector in message_input_selectors:
                    try:
                        message_input = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        if message_input and message_input.is_displayed():
                            logger.info(f"Found message input using selector: {selector}")
                            break
                    except:
                        continue
                
                if not message_input:
                    logger.error(f"Could not find message input for {identifier}")
                    return False
                
                # Clear existing content and wait briefly
                message_input.clear()
                time.sleep(random.uniform(0.5, 1))
                
                # Type message character by character with small random delays
                self._type_like_human(message_input, message)
                time.sleep(random.uniform(1, 2))
                
                # Find and click send button
                send_button = None
                send_button_selectors = [
                    "//button[@data-tsid='button_send'][@class='primary-okmsg']",  # Exact match
                    "//button[@data-l='t,sendButton']",  # Data attribute match
                    "//button[contains(@class, 'primary-okmsg')]",  # Class match
                    "//button[@title='Send']",  # Title match
                    "//button[contains(@class, 'button-pro')]",  # Generic button class
                    # Additional backup selectors
                    "//button[contains(@class, 'messaging_submit')]",
                    "//button[contains(@class, 'send-button')]"
                ]
                
                for selector in send_button_selectors:
                    try:
                        send_button = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        if send_button and send_button.is_displayed():
                            logger.info(f"Found send button using selector: {selector}")
                            break
                    except:
                        continue
                
                if not send_button:
                    logger.error(f"Could not find send button for {identifier}")
                    return False
                
                # Click the send button and wait for confirmation
                send_button.click()
                time.sleep(random.uniform(2, 3))
                
                # Verify message was sent
                try:
                    # Look for sent message confirmation or new message in chat
                    sent_selectors = [
                        "//div[contains(@class, 'msg_success')]",
                        "//div[contains(@class, 'message-sent')]",
                        "//div[contains(@class, 'msg-success')]"
                    ]
                    
                    for selector in sent_selectors:
                        try:
                            WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.XPATH, selector))
                            )
                            logger.info(f"Message sent confirmation found using selector: {selector}")
                            break
                        except:
                            continue
                except:
                    logger.warning("Could not find sent confirmation, but proceeding")
                
                logger.info(f"Successfully sent message to {identifier}")
                return True
                
            except Exception as e:
                logger.error(f"Error in message composition for {identifier}: {str(e)}")
                return False
            
        except Exception as e:
            logger.error(f"Error sending message to {identifier}: {str(e)}")
            return False 