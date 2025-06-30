import os
import logging
import threading
import time
from datetime import datetime
import json
import pandas as pd
from markupsafe import Markup
import requests
from threading import Thread

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
from forms import AccountForm, CampaignForm
from models import db, Account, Campaign, CampaignAccount, Lead, Message, LoginType, ProxyType
from automation import OdnoklassnikiBot
from runner import CampaignRunner
from flask_wtf.csrf import CSRFProtect

# Initialize Flask app
app = Flask(__name__, instance_relative_config=True)

# Ensure the instance folder exists
try:
    os.makedirs(app.instance_path)
except OSError:
    pass

# Configure app
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(app.instance_path, "odnoklassniki.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.abspath('uploads')
app.config['WTF_CSRF_ENABLED'] = True

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db.init_app(app)

# Initialize SocketIO with CSRF exempt
socketio = SocketIO(app, cors_allowed_origins="*")

# Create database tables
with app.app_context():
    db.create_all()

# Add nl2br filter
@app.template_filter('nl2br')
def nl2br_filter(text):
    if not text:
        return ""
    return Markup(text.replace('\n', '<br>'))

@app.route('/get_messages', methods=['POST'])
def get_messages():
    try:
        data = request.get_json()
        account_ids = data.get('account_ids', [])
        
        # Query messages
        query = Message.query
        if account_ids:
            query = query.filter(Message.account_id.in_(account_ids))
        
        messages = query.order_by(Message.received_at.desc()).all()
        
        # Get unread counts for each account
        unread_counts = {}
        for account_id in account_ids:
            unread_counts[account_id] = Message.query.filter_by(
                account_id=account_id,
                is_read=False
            ).count()
        
        return jsonify({
            'messages': [msg.to_dict() for msg in messages],
            'unread_counts': unread_counts
        })
    except Exception as e:
        logger.error(f"Error getting messages: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/mark_messages_read', methods=['POST'])
def mark_messages_read():
    try:
        data = request.get_json()
        account_ids = data.get('account_ids', [])
        
        # Mark messages as read
        query = Message.query
        if account_ids:
            query = query.filter(Message.account_id.in_(account_ids))
        
        query.update({Message.is_read: True})
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error marking messages as read: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/refresh_messages/<int:account_id>')
def refresh_messages(account_id):
    try:
        # Simulate loading time
        time.sleep(5)
        
        return jsonify({
            'status': 'success',
            'message': 'No messages for now, check later :)'
        })
            
    except Exception as e:
        logger.error(f"Error refreshing messages: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/')
def index():
    accounts = Account.query.all()
    campaigns = Campaign.query.all()
    return render_template('index.html', accounts=accounts, campaigns=campaigns)

@app.route('/accounts', methods=['GET', 'POST'])
def accounts():
    form = AccountForm()
    if form.validate_on_submit():
        try:
            logger.info(f"Creating account with {form.login_type.data}: {form.login.data}")
            
            # Only include proxy data if a proxy type is selected
            proxy_type = None
            proxy_host = None
            proxy_port = None
            proxy_username = None
            proxy_password = None
            
            if form.proxy_type.data:
                proxy_type = ProxyType[form.proxy_type.data]
                proxy_host = form.proxy_host.data
                proxy_port = form.proxy_port.data
                proxy_username = form.proxy_username.data
                proxy_password = form.proxy_password.data
            
            account = Account(
                login_type=LoginType[form.login_type.data.upper()],
                login=form.login.data,
                password=form.password.data,
                proxy_type=proxy_type,
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                proxy_username=proxy_username,
                proxy_password=proxy_password,
                is_active=True
            )
            db.session.add(account)
            db.session.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'success',
                    'message': 'Account added successfully!'
                })
            
            flash('Account added successfully!', 'success')
            logger.info(f"Account created successfully: {account.id}")
            return redirect(url_for('accounts'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating account: {str(e)}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'error',
                    'message': f'Error creating account: {str(e)}'
                })
            
            flash(f'Error creating account: {str(e)}', 'danger')
    else:
        if form.errors:
            logger.error(f"Form validation errors: {form.errors}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'error',
                    'message': 'Validation error',
                    'errors': form.errors
                })
            
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{field}: {error}', 'danger')
    
    accounts = Account.query.all()
    return render_template('accounts.html', form=form, accounts=accounts)

@app.route('/campaigns', methods=['GET', 'POST'])
def campaigns():
    form = CampaignForm()
    
    # Get all accounts for the form
    form.accounts.choices = [(a.id, f"{a.login} ({a.login_type.name})") for a in Account.query.all()]
    
    if form.validate_on_submit():
        try:
            # Create campaign
            campaign = Campaign(
                name=form.name.data,
                message_template=form.message_template.data,
                min_delay=form.min_delay.data,
                max_delay=form.max_delay.data,
                status='pending'
            )
            db.session.add(campaign)
            db.session.commit()
            
            # Add selected accounts to campaign
            selected_accounts = form.accounts.data
            for account_id in selected_accounts:
                campaign_account = CampaignAccount(
                    campaign_id=campaign.id,
                    account_id=account_id
                )
                db.session.add(campaign_account)
            db.session.commit()
            
            # Process uploaded file
            if form.leads_file.data:
                file = form.leads_file.data
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Read Excel file
                df = pd.read_excel(filepath)
                
                # Get valid leads
                valid_leads = []
                for _, row in df.iterrows():
                    url = str(row.iloc[0]).strip()  # Get first column
                    if url and url != 'nan':
                        # Ensure URL has proper format
                        if not url.startswith('http'):
                            url = f'https://{url}'
                        if 'ok.ru/profile/' not in url and 'ok.ru/' in url:
                            # Convert username URL to profile URL
                            username = url.split('ok.ru/')[-1].split('/')[0]
                            url = f'https://ok.ru/profile/{username}'
                        valid_leads.append(url)
                
                if valid_leads:
                    # Calculate leads per account
                    leads_per_account = len(valid_leads) // len(selected_accounts)
                    remainder = len(valid_leads) % len(selected_accounts)
                    
                    # Distribute leads among accounts
                    lead_index = 0
                    for idx, account_id in enumerate(selected_accounts):
                        # Calculate how many leads this account gets
                        account_leads_count = leads_per_account + (1 if idx < remainder else 0)
                        
                        # Assign leads to this account
                        for _ in range(account_leads_count):
                            if lead_index < len(valid_leads):
                                lead = Lead(
                                    campaign_id=campaign.id,
                                    account_id=account_id,
                                    profile_url=valid_leads[lead_index],
                                    status='pending'
                                )
                                db.session.add(lead)
                                lead_index += 1
                                
                                # Update campaign account leads count
                                campaign_account = CampaignAccount.query.filter_by(
                                    campaign_id=campaign.id,
                                    account_id=account_id
                                ).first()
                                if campaign_account:
                                    campaign_account.leads_count += 1
                
                db.session.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'success',
                    'message': 'Campaign created successfully!'
                })
            
            flash('Campaign created successfully!', 'success')
            return redirect(url_for('campaigns'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating campaign: {str(e)}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'error',
                    'message': f'Error creating campaign: {str(e)}'
                })
            
            flash(f'Error creating campaign: {str(e)}', 'danger')
    else:
        if form.errors:
            logger.error(f"Form validation errors: {form.errors}")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'error',
                    'message': 'Validation error',
                    'errors': form.errors
                })
            
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{field}: {error}', 'danger')
    
    # Get campaigns with additional info
    campaigns_with_info = []
    for campaign in Campaign.query.all():
        total_leads = Lead.query.filter_by(campaign_id=campaign.id).count()
        processed_leads = Lead.query.filter(
            Lead.campaign_id == campaign.id,
            Lead.status.in_(['completed', 'failed'])
        ).count()
        
        campaign_info = {
            'id': campaign.id,
            'name': campaign.name,
            'status': campaign.status,
            'created_at': campaign.created_at,
            'total_leads': total_leads,
            'processed_leads': processed_leads
        }
        campaigns_with_info.append(campaign_info)
    
    return render_template('campaigns.html', form=form, campaigns=campaigns_with_info)

@app.route('/delete_account/<int:id>', methods=['POST'])
def delete_account(id):
    try:
        account = Account.query.get_or_404(id)
        
        # Delete in this order to handle foreign key constraints
        try:
            # First delete all leads associated with this account
            Lead.query.filter_by(account_id=id).delete()
            db.session.commit()
            
            # Then delete all campaign accounts
            CampaignAccount.query.filter_by(account_id=id).delete()
            db.session.commit()
            
            # Finally delete the account
            db.session.delete(account)
            db.session.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'success',
                    'message': 'Account deleted successfully!'
                })
            
            flash('Account deleted successfully!', 'success')
            return redirect(url_for('accounts'))
            
        except Exception as inner_e:
            db.session.rollback()
            logger.error(f"Database error while deleting account {id}: {str(inner_e)}")
            raise
            
    except Exception as e:
        logger.error(f"Error deleting account {id}: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'status': 'error',
                'message': f'Error deleting account: {str(e)}'
            }), 500
        
        flash(f'Error deleting account: {str(e)}', 'danger')
        return redirect(url_for('accounts'))

@app.route('/delete_campaign/<int:campaign_id>', methods=['POST'])
def delete_campaign(campaign_id):
    try:
        campaign = Campaign.query.get_or_404(campaign_id)
        
        # Delete in this order to handle foreign key constraints
        try:
            # Delete leads first
            Lead.query.filter_by(campaign_id=campaign_id).delete()
            db.session.commit()
            
            # Delete campaign accounts
            CampaignAccount.query.filter_by(campaign_id=campaign_id).delete()
            db.session.commit()
            
            # Finally delete the campaign
            db.session.delete(campaign)
            db.session.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'success',
                    'message': 'Campaign deleted successfully!'
                })
            
            flash('Campaign deleted successfully!', 'success')
            return redirect(url_for('campaigns'))
            
        except Exception as inner_e:
            db.session.rollback()
            logger.error(f"Database error while deleting campaign {campaign_id}: {str(inner_e)}")
            raise
            
    except Exception as e:
        logger.error(f"Error deleting campaign {campaign_id}: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'status': 'error',
                'message': f'Error deleting campaign: {str(e)}'
            }), 500
        
        flash(f'Error deleting campaign: {str(e)}', 'danger')
        return redirect(url_for('campaigns'))

@app.route('/inbox')
def inbox():
    accounts = Account.query.all()
    return render_template('inbox.html', accounts=accounts)

@app.route('/test_proxy', methods=['POST'])
def test_proxy():
    try:
        data = request.get_json()
        
        # Extract proxy details
        proxy_type = data.get('proxy_type')
        proxy_host = data.get('proxy_host')
        proxy_port = data.get('proxy_port')
        proxy_username = data.get('proxy_username')
        proxy_password = data.get('proxy_password')
        
        # Skip test if no proxy type selected
        if not proxy_type:
            return jsonify({
                'status': 'warning',
                'message': 'No proxy type selected, skipping test'
            })
        
        # Validate required fields
        if not all([proxy_host, proxy_port]):
            return jsonify({
                'status': 'error',
                'message': 'Proxy host and port are required'
            })
        
        # Format proxy URL
        if proxy_username and proxy_password:
            proxy_url = f"{proxy_type}://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
        else:
            proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
        
        # Configure proxy for requests
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        # Test proxy with a request to a test URL
        response = requests.get('https://www.google.com', proxies=proxies, timeout=10)
        
        if response.status_code == 200:
            return jsonify({
                'status': 'success',
                'message': 'Proxy test successful!'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Proxy test failed with status code: {response.status_code}'
            })
            
    except requests.exceptions.ProxyError as e:
        return jsonify({
            'status': 'error',
            'message': 'Proxy connection failed. Please check your proxy settings.'
        })
    except requests.exceptions.Timeout:
        return jsonify({
            'status': 'error',
            'message': 'Proxy test timed out. The proxy may be too slow.'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Proxy test failed: {str(e)}'
        })

@app.route('/edit_account/<int:account_id>', methods=['POST'])
def edit_account(account_id):
    try:
        account = Account.query.get_or_404(account_id)
        data = request.get_json()
        
        # Update fields
        if 'login' in data:
            account.login = data['login']
        if 'password' in data:
            account.password = data['password']
        if 'login_type' in data:
            account.login_type = LoginType[data['login_type'].upper()]
        if 'is_active' in data:
            account.is_active = data['is_active']
            
        # Update proxy settings
        if 'proxy_type' in data:
            account.proxy_type = ProxyType[data['proxy_type']] if data['proxy_type'] else None
        if 'proxy_host' in data:
            account.proxy_host = data['proxy_host']
        if 'proxy_port' in data:
            account.proxy_port = data['proxy_port']
        if 'proxy_username' in data:
            account.proxy_username = data['proxy_username']
        if 'proxy_password' in data:
            account.proxy_password = data['proxy_password']
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Account updated successfully!'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error updating account: {str(e)}'
        }), 500

@app.route('/campaign/<int:campaign_id>/distribution')
def get_campaign_distribution(campaign_id):
    try:
        # Get campaign
        campaign = Campaign.query.get_or_404(campaign_id)
        
        # Get total leads
        total_leads = Lead.query.filter_by(campaign_id=campaign_id).count()
        
        # Get lead status distribution
        status_distribution = {}
        for status in ['pending', 'completed', 'failed']:
            count = Lead.query.filter_by(
                campaign_id=campaign_id,
                status=status
            ).count()
            status_distribution[status] = count
        
        # Get account distribution
        account_distribution = []
        campaign_accounts = CampaignAccount.query.filter_by(campaign_id=campaign_id).all()
        
        for ca in campaign_accounts:
            account = Account.query.get(ca.account_id)
            account_distribution.append({
                'account': account.login,
                'messages_sent': ca.messages_sent
            })
        
        return jsonify({
            'total_leads': total_leads,
            'status_distribution': status_distribution,
            'account_distribution': account_distribution
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error getting campaign distribution: {str(e)}'
        }), 500

@app.route('/campaign/<int:id>/start', methods=['POST'])
def start_campaign(id):
    try:
        campaign = Campaign.query.get_or_404(id)
        
        # Check if campaign is already running
        if campaign.status == 'running':
            return jsonify({
                'status': 'error',
                'message': 'Campaign is already running'
            }), 400
        
        # Check if campaign has accounts
        campaign_accounts = CampaignAccount.query.filter_by(campaign_id=id).all()
        if not campaign_accounts:
            return jsonify({
                'status': 'error',
                'message': 'No accounts assigned to campaign'
            }), 400
        
        # Check if campaign has leads
        leads = Lead.query.filter_by(campaign_id=id, status='pending').count()
        if not leads:
            return jsonify({
                'status': 'error',
                'message': 'No pending leads in campaign'
            }), 400
        
        # Update campaign status
        campaign.status = 'running'
        campaign.started_at = datetime.utcnow()
        db.session.commit()
        
        # Start campaign runner in a separate thread
        runner = CampaignRunner(id, socketio, app)
        thread = Thread(target=runner.run)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': 'Campaign started successfully'
        })
        
    except Exception as e:
        logger.error(f"Error starting campaign: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error starting campaign: {str(e)}'
        }), 500

@app.route('/campaign/<int:id>/stop', methods=['POST'])
def stop_campaign(id):
    try:
        campaign = Campaign.query.get_or_404(id)
        
        # Check if campaign is running
        if campaign.status != 'running':
            return jsonify({
                'status': 'error',
                'message': 'Campaign is not running'
            }), 400
        
        # Update campaign status
        campaign.status = 'stopped'
        campaign.stopped_at = datetime.utcnow()
        db.session.commit()
        
        # Emit stop event to all clients
        socketio.emit('campaign_stopped', {
            'campaign_id': id,
            'message': 'Campaign stopped by user'
        })
        
        return jsonify({
            'status': 'success',
            'message': 'Campaign stopped successfully'
        })
        
    except Exception as e:
        logger.error(f"Error stopping campaign: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error stopping campaign: {str(e)}'
        }), 500

@app.route('/get_account/<int:account_id>')
def get_account(account_id):
    try:
        account = Account.query.get_or_404(account_id)
        return jsonify({
            'id': account.id,
            'login': account.login,
            'login_type': account.login_type.name,
            'is_active': account.is_active,
            'proxy_type': account.proxy_type.name if account.proxy_type else None,
            'proxy_host': account.proxy_host,
            'proxy_port': account.proxy_port,
            'proxy_username': account.proxy_username,
            'proxy_password': account.proxy_password
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error getting account: {str(e)}'
        }), 500

@socketio.on('campaign_update')
def handle_campaign_update(data):
    """Handle campaign progress updates"""
    try:
        # Broadcast update to all clients
        socketio.emit('campaign_progress', data)
    except Exception as e:
        logger.error(f"Error handling campaign update: {str(e)}")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8081, debug=True) 