from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from enum import Enum

db = SQLAlchemy()

class ProxyType(Enum):
    HTTP = 'http'
    HTTPS = 'https'
    SOCKS4 = 'socks4'
    SOCKS5 = 'socks5'

class LoginType(Enum):
    PHONE = 'phone'
    EMAIL = 'email'

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login_type = db.Column(db.Enum(LoginType), nullable=False)
    login = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    proxy_type = db.Column(db.Enum(ProxyType), nullable=True)
    proxy_host = db.Column(db.String(255), nullable=True)
    proxy_port = db.Column(db.Integer, nullable=True)
    proxy_username = db.Column(db.String(255), nullable=True)
    proxy_password = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    message_template = db.Column(db.Text, nullable=False)
    min_delay = db.Column(db.Integer, nullable=False)  # Delay in seconds
    max_delay = db.Column(db.Integer, nullable=False)  # Delay in seconds
    status = db.Column(db.String(20), default='pending')  # pending, running, paused, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_processed_lead_id = db.Column(db.Integer, nullable=True)  # Track the last processed lead
    
    campaign_accounts = db.relationship('CampaignAccount', backref='campaign', lazy=True, cascade='all, delete-orphan')
    leads = db.relationship('Lead', backref='campaign', lazy=True, cascade='all, delete-orphan')

class CampaignAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id', ondelete='CASCADE'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    leads_count = db.Column(db.Integer, default=0)
    messages_sent = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    account = db.relationship('Account', backref='campaign_accounts')

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id', ondelete='CASCADE'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    profile_url = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    message_sent = db.Column(db.Boolean, default=False)
    processed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    account = db.relationship('Account', backref='leads')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    sender_id = db.Column(db.String(255), nullable=False)  # OK.ru sender ID
    sender_name = db.Column(db.String(255), nullable=False)  # OK.ru sender name
    message_text = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    ok_message_id = db.Column(db.String(255), nullable=False)  # Original OK.ru message ID
    received_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    account = db.relationship('Account', backref='messages')

    def to_dict(self):
        return {
            'id': self.id,
            'sender': self.sender_name,
            'account': self.account.login,
            'text': self.message_text,
            'read': self.is_read,
            'time': self.received_at.strftime('%Y-%m-%d %H:%M'),
        } 