from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, TextAreaField, IntegerField, FileField, SelectMultipleField, RadioField
from wtforms.validators import DataRequired, Optional, NumberRange, ValidationError, Email, Regexp

class AccountForm(FlaskForm):
    login_type = RadioField('Login Type', 
                          choices=[('phone', 'Phone Number'), ('email', 'Email')],
                          default='phone',
                          validators=[DataRequired()])
    login = StringField('Phone Number / Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    proxy_type = SelectField('Proxy Type', choices=[('', 'No Proxy'), ('HTTP', 'HTTP'), ('SOCKS5', 'SOCKS5')])
    proxy_host = StringField('Proxy Host', validators=[Optional()])
    proxy_port = IntegerField('Proxy Port', validators=[Optional(), NumberRange(min=1, max=65535, message="Port must be between 1 and 65535")])
    proxy_username = StringField('Proxy Username', validators=[Optional()])
    proxy_password = PasswordField('Proxy Password', validators=[Optional()])

    def validate_login(self, field):
        if self.login_type.data == 'phone':
            # Remove any spaces, dashes, or parentheses from phone number
            phone = ''.join(filter(str.isdigit, field.data))
            if not phone.isdigit() or len(phone) < 10 or len(phone) > 15:
                raise ValidationError('Please enter a valid phone number (10-15 digits)')
            field.data = phone  # Store cleaned phone number
        else:  # email
            # Use WTForms email validator
            email_validator = Email(message='Please enter a valid email address')
            email_validator(self, field)

    def validate_proxy_fields(self, **kwargs):
        if self.proxy_type.data:  # If proxy is selected
            if not self.proxy_host.data:
                self.proxy_host.errors.append('Proxy host is required when using a proxy')
                return False
            if not self.proxy_port.data:
                self.proxy_port.errors.append('Proxy port is required when using a proxy')
                return False
        return True

    def validate(self, extra_validators=None):
        initial_validation = super().validate(extra_validators=extra_validators)
        if not initial_validation:
            return False
        return self.validate_proxy_fields()

class CampaignForm(FlaskForm):
    name = StringField('Campaign Name', validators=[DataRequired()])
    accounts = SelectMultipleField('Select Accounts', coerce=int, validators=[DataRequired()])
    leads_file = FileField('Upload Leads (CSV/Excel)', validators=[DataRequired()])
    message_template = TextAreaField('Message Template', validators=[DataRequired()])
    min_delay = IntegerField('Minimum Delay (seconds)', 
                            validators=[DataRequired(), NumberRange(min=5)],
                            default=15)
    max_delay = IntegerField('Maximum Delay (seconds)', 
                            validators=[DataRequired(), NumberRange(min=5)],
                            default=30) 