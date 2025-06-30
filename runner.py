import logging
import random
import time
from datetime import datetime
from typing import List, Dict
from automation import OdnoklassnikiBot
from models import db, Campaign, Account, Lead, CampaignAccount
from flask_socketio import SocketIO
from flask import current_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CampaignRunner:
    def __init__(self, campaign_id, socketio, app):
        self.app = app
        self.campaign_id = campaign_id
        self.running = False
        self.current_bot = None
        self.logger = logging.getLogger(__name__)
        self.socketio = socketio

    def stop(self):
        """Stop the campaign"""
        self.running = False
        if self.current_bot:
            self.current_bot.quit()

    def emit_progress(self, account_id, message, status='info'):
        """Emit progress update via Socket.IO"""
        self.socketio.emit('campaign_update', {
            'campaign_id': self.campaign_id,
            'account_id': account_id,
            'message': message,
            'status': status
        })

    def get_proxy_config(self, account):
        """Get proxy configuration for an account"""
        if not account.proxy_type or not account.proxy_host or not account.proxy_port:
            return None
        
        proxy_config = {
            'host': account.proxy_host,
            'port': account.proxy_port,
            'type': account.proxy_type.value.lower()  # Convert enum to lowercase string
        }
        
        # Add authentication if provided
        if account.proxy_username and account.proxy_password:
            proxy_config['username'] = account.proxy_username
            proxy_config['password'] = account.proxy_password
        
        return proxy_config

    def run(self):
        """Run the campaign"""
        try:
            self.running = True
            
            # Get campaign accounts and leads within app context
            with self.app.app_context():
                campaign = Campaign.query.get(self.campaign_id)
                if not campaign:
                    self.emit_progress(None, "Campaign not found", 'error')
                    return
                    
                campaign_accounts = CampaignAccount.query.filter_by(campaign_id=self.campaign_id).all()
                total_leads = Lead.query.filter_by(campaign_id=self.campaign_id, status='pending').count()
                
                if not campaign_accounts:
                    self.emit_progress(None, "No accounts found for campaign", 'error')
                    return
                    
                if not total_leads:
                    self.emit_progress(None, "No pending leads found for campaign", 'error')
                    return
                
                # Calculate leads per account
                leads_per_account = total_leads // len(campaign_accounts)
                remainder = total_leads % len(campaign_accounts)
                
                # Process each account
                for idx, campaign_account in enumerate(campaign_accounts):
                    if not self.running:
                        break
                        
                    account = Account.query.get(campaign_account.account_id)
                    
                    # Calculate leads for this account (add one extra if there's remainder)
                    account_leads_count = leads_per_account + (1 if idx < remainder else 0)
                    
                    # Get leads for this account
                    leads = Lead.query.filter_by(
                        campaign_id=self.campaign_id,
                        status='pending'
                    ).limit(account_leads_count).all()
                    
                    if leads:
                        try:
                            self.emit_progress(account.id, f"Starting browser for account {account.login}...")
                            
                            # Initialize browser with proxy if configured
                            bot = OdnoklassnikiBot(proxy_config=self.get_proxy_config(account))
                            
                            # Setup the driver
                            if not bot.setup_driver():
                                self.emit_progress(account.id, "Failed to initialize browser", 'error')
                                continue
                                
                            self.current_bot = bot
                            
                            # Login to account
                            if not bot.login(account.login, account.password):
                                self.emit_progress(account.id, "Failed to login", 'error')
                                continue
                            
                            # Process leads
                            for lead in leads:
                                if not self.running:
                                    self.emit_progress(account.id, "Campaign stopped by user.", 'warning')
                                    return
                                    
                                try:
                                    # Send message
                                    message_sent = bot.send_message(
                                        lead.profile_url,  # Use profile_url instead of username
                                        campaign.message_template,
                                        campaign.min_delay,
                                        campaign.max_delay
                                    )
                                    
                                    # Update lead status
                                    lead.status = 'completed' if message_sent else 'failed'
                                    lead.message_sent = message_sent
                                    lead.processed_at = datetime.utcnow()
                                    if not message_sent:
                                        lead.error_message = "Failed to send message"
                                    
                                    # Update campaign account stats
                                    if message_sent:
                                        campaign_account.messages_sent += 1
                                    
                                    db.session.commit()
                                    
                                    # Emit progress
                                    status = 'success' if message_sent else 'error'
                                    self.emit_progress(
                                        account.id,
                                        f"Message {'sent to' if message_sent else 'failed for'} {lead.profile_url}",
                                        status
                                    )
                                    
                                    # Add random delay between messages
                                    if campaign.min_delay and campaign.max_delay:
                                        delay = random.uniform(campaign.min_delay, campaign.max_delay)
                                        time.sleep(delay)
                                    
                                except Exception as e:
                                    self.logger.error(f"Error processing lead {lead.profile_url}: {str(e)}")
                                    self.emit_progress(account.id, f"Error: {str(e)}", 'error')
                                    
                                    lead.status = 'failed'
                                    lead.error_message = str(e)
                                    db.session.commit()
                        
                        except Exception as e:
                            self.logger.error(f"Error with account {account.login}: {str(e)}")
                            self.emit_progress(account.id, f"Error: {str(e)}", 'error')
                        
                        finally:
                            if self.current_bot:
                                self.current_bot.quit()
                                self.current_bot = None
                
                # Update campaign status when finished
                campaign.status = 'completed' if self.running else 'stopped'
                db.session.commit()
                
                status = "success" if campaign.status == 'completed' else "warning"
                self.emit_progress(None, f"Campaign {campaign.status}", status)
                
        except Exception as e:
            self.logger.error(f"Campaign error: {str(e)}")
            with self.app.app_context():
                campaign = Campaign.query.get(self.campaign_id)
                if campaign:
                    campaign.status = 'failed'
                    db.session.commit()
            self.emit_progress(None, f"Error: {str(e)}", 'error') 