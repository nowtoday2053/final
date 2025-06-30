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
    logger.info(f"Current number of accounts: {len(accounts)}")
    return render_template('accounts.html', form=form, accounts=accounts)

@app.route('/campaigns', methods=['GET', 'POST'])
def campaigns():
    form = CampaignForm()
    form.accounts.choices = [(a.id, a.login) for a in Account.query.all()]
    
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
            
            # Save leads file
            leads_file = form.leads_file.data
            filename = secure_filename(leads_file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            leads_file.save(filepath)
            
            # Process leads file
            try:
                df = pd.read_excel(filepath)
                profile_column = df.columns[0]  # Assume first column contains profile URLs/IDs
                total_leads = len(df)
                
                # Get selected accounts
                selected_accounts = form.accounts.data
                total_accounts = len(selected_accounts)
                
                # Calculate leads distribution
                base_leads_per_account = total_leads // total_accounts
                remainder = total_leads % total_accounts
                
                current_index = 0
                
                # Distribute leads among accounts
                for i, account_id in enumerate(selected_accounts):
                    # Calculate leads for this account (add one extra if there's remainder)
                    account_leads_count = base_leads_per_account + (1 if i < remainder else 0)
                    end_index = current_index + account_leads_count
                    
                    # Create campaign account
                    campaign_account = CampaignAccount(
                        campaign_id=campaign.id,
                        account_id=account_id,
                        leads_count=account_leads_count,
                        messages_sent=0
                    )
                    db.session.add(campaign_account)
                    
                    # Create leads for this account
                    account_leads = df[profile_column][current_index:end_index]
                    for identifier in account_leads:
                        lead = Lead(
                            campaign_id=campaign.id,
                            account_id=account_id,
                            profile_url=identifier,
                            status='pending'
                        )
                        db.session.add(lead)
                        logger.info(f"Added lead {identifier} for account {account_id}")
                    
                    current_index = end_index
                
                db.session.commit()
                flash('Campaign created successfully!', 'success')
                
            except Exception as e:
                logger.error(f"Error processing leads file: {str(e)}")
                db.session.rollback()
                flash(f'Error processing leads file: {str(e)}', 'danger')
                return redirect(url_for('campaigns'))
            
            finally:
                # Clean up the uploaded file
                try:
                    os.remove(filepath)
                except:
                    pass
                
            return redirect(url_for('campaigns'))
            
        except Exception as e:
            logger.error(f"Error creating campaign: {str(e)}")
            flash(f'Error creating campaign: {str(e)}', 'danger')
            return redirect(url_for('campaigns'))
    
    campaigns = Campaign.query.all()
    return render_template('campaigns.html', form=form, campaigns=campaigns)

@app.route('/delete_account/<int:id>', methods=['POST'])
def delete_account(id):
    account = Account.query.get_or_404(id)
    db.session.delete(account)
    db.session.commit()
    flash('Account deleted successfully!', 'success')
    return redirect(url_for('accounts'))

@app.route('/delete_campaign/<int:campaign_id>', methods=['POST'])
def delete_campaign(campaign_id):
    try:
        campaign = Campaign.query.get_or_404(campaign_id)
        
        # Delete the campaign - related records will be deleted automatically due to cascade
        db.session.delete(campaign)
        db.session.commit()
        
        flash('Campaign deleted successfully', 'success')
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting campaign: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to delete campaign. Please try again.'
        }), 500

@app.route('/inbox')
def inbox():
    accounts = Account.query.all()
    return render_template('inbox.html', accounts=accounts)

@app.route('/test_proxy', methods=['POST'])
def test_proxy():
    try:
        data = request.get_json()
        
        # Create proxy URL
        proxy_type = data.get('proxy_type', 'http').lower()
        proxy_host = data.get('proxy_host')
        proxy_port = data.get('proxy_port')
        proxy_username = data.get('proxy_username')
        proxy_password = data.get('proxy_password')
        
        if not all([proxy_host, proxy_port]):
            return jsonify({
                'status': 'error',
                'message': 'Proxy host and port are required'
            }), 400
            
        # Build proxy URL
        if proxy_username and proxy_password:
            proxy_url = f"{proxy_type}://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
        else:
            proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
            
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        # Test proxy with a request to ok.ru
        response = requests.get('https://ok.ru', 
                              proxies=proxies, 
                              timeout=10,
                              verify=False)  # Skip SSL verification for testing
        
        if response.status_code == 200:
            return jsonify({
                'status': 'success',
                'message': 'Proxy connection successful!'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Proxy test failed with status code: {response.status_code}'
            }), 400
            
    except requests.exceptions.ProxyError as e:
        logger.error(f"Proxy error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Invalid proxy configuration or proxy is not responding'
        }), 400
    except requests.exceptions.Timeout:
        return jsonify({
            'status': 'error',
            'message': 'Proxy connection timed out'
        }), 400
    except Exception as e:
        logger.error(f"Error testing proxy: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/edit_account/<int:account_id>', methods=['POST'])
def edit_account(account_id):
    try:
        data = request.get_json()
        account = Account.query.get_or_404(account_id)
        
        # Update account fields
        account.login_type = LoginType[data['login_type'].upper()]
        account.login = data['login']
        account.password = data['password']
        
        # Update proxy settings if provided
        if data.get('proxy_type'):
            account.proxy_type = ProxyType[data['proxy_type']]
            account.proxy_host = data['proxy_host']
            account.proxy_port = data['proxy_port']
            account.proxy_username = data['proxy_username']
            account.proxy_password = data['proxy_password']
        else:
            # Clear proxy settings if not provided
            account.proxy_type = None
            account.proxy_host = None
            account.proxy_port = None
            account.proxy_username = None
            account.proxy_password = None
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Account updated successfully!'
        })
        
    except Exception as e:
        logger.error(f"Error updating account {account_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred while updating the account'
        }), 500

@app.route('/campaign/<int:campaign_id>/distribution')
def get_campaign_distribution(campaign_id):
    campaign = Campaign.query.get_or_404(campaign_id)
    
    # Get all campaign accounts
    campaign_accounts = CampaignAccount.query.filter_by(campaign_id=campaign_id).all()
    
    # Get total number of leads
    total_leads = Lead.query.filter_by(campaign_id=campaign_id).count()
    
    # Calculate leads per account (evenly distributed)
    leads_per_account = total_leads // len(campaign_accounts) if campaign_accounts else 0
    remainder = total_leads % len(campaign_accounts) if campaign_accounts else 0
    
    distribution = []
    for idx, ca in enumerate(campaign_accounts):
        account = Account.query.get(ca.account_id)
        # Add one more lead to first 'remainder' accounts to handle uneven distribution
        account_leads = leads_per_account + (1 if idx < remainder else 0)
        
        # Get number of processed leads for this account
        processed_leads = Lead.query.filter_by(
            campaign_id=campaign_id,
            assigned_account_id=account.id,
            status='completed'
        ).count()
        
        distribution.append({
            'account_login': account.login,
            'total_leads': account_leads,
            'processed_leads': processed_leads
        })
    
    return jsonify({
        'campaign_id': campaign_id,
        'distribution': distribution
    })

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
            
        # Get campaign accounts
        campaign_accounts = CampaignAccount.query.filter_by(campaign_id=id).all()
        if not campaign_accounts:
            return jsonify({
                'status': 'error',
                'message': 'No accounts assigned to this campaign'
            }), 400
            
        # Get campaign leads
        leads = Lead.query.filter_by(campaign_id=id, status='pending').all()
        if not leads:
            return jsonify({
                'status': 'error',
                'message': 'No pending leads found for this campaign'
            }), 400
            
        # Create and start campaign runner
        app.socketio = socketio  # Attach socketio instance to app
        runner = CampaignRunner(app, campaign)
        app.campaign_runners[campaign.id] = runner
        
        # Start the campaign in a background thread
        thread = Thread(target=runner.run)
        thread.daemon = True
        thread.start()
        
        # Update campaign status
        campaign.status = 'running'
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Campaign started successfully'
        })
        
    except Exception as e:
        logger.error(f"Error starting campaign: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/campaign/<int:id>/stop', methods=['POST'])
def stop_campaign(id):
    try:
        campaign = Campaign.query.get_or_404(id)
        
        # Check if campaign is already stopped
        if campaign.status != 'running':
            return jsonify({
                'status': 'error',
                'message': 'Campaign is not running'
            }), 400
            
        # Stop campaign runner if exists
        runner = app.campaign_runners.get(campaign.id)
        if runner:
            runner.stop()
            del app.campaign_runners[campaign.id]
        
        # Update campaign status
        campaign.status = 'stopped'
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Campaign stopped successfully'
        })
        
    except Exception as e:
        logger.error(f"Error stopping campaign: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/get_account/<int:account_id>')
def get_account(account_id):
    try:
        account = Account.query.get_or_404(account_id)
        return jsonify({
            'status': 'success',
            'data': {
                'login': account.login,
                'proxy_type': account.proxy_type.value if account.proxy_type else None,
                'proxy_host': account.proxy_host,
                'proxy_port': account.proxy_port,
                'proxy_username': account.proxy_username,
                'proxy_password': account.proxy_password
            }
        })
    except Exception as e:
        logger.error(f"Error getting account {account_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@socketio.on('campaign_update')
def handle_campaign_update(data):
    """Handle campaign updates via Socket.IO"""
    campaign_id = data.get('campaign_id')
    status = data.get('status')
    leads_processed = data.get('leads_processed', 0)
    
    # Broadcast the update to all connected clients
    emit('campaign_update', {
        'campaign_id': campaign_id,
        'status': status,
        'leads_processed': leads_processed
    }, broadcast=True)

# Initialize campaign runners dict
app.campaign_runners = {}

if __name__ == '__main__':
    try:
        # Try port 8080 first
        port = 8080
        retries = 3
        
        while retries > 0:
            try:
                socketio.run(
                    app,
                    host='0.0.0.0',
                    port=port,
                    debug=True,
                    use_reloader=False  # Disable reloader to prevent duplicate processes
                )
                break
            except OSError:
                logger.warning(f"Port {port} is in use, trying port {port + 1}")
                port += 1
                retries -= 1
                
                if retries == 0:
                    logger.error("Could not find an available port")
                    raise
                
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        raise 