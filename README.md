# Odnoklassniki Outreach Automation Tool

A web-based tool for automating outreach campaigns on Odnoklassniki using Selenium and undetected-chromedriver.

## Features

- **Account Management**
  - Add multiple Odnoklassniki accounts
  - Configure HTTP/SOCKS5 proxies for each account
  - Monitor account status and activity

- **Campaign System**
  - Create campaigns with customizable settings
  - Upload leads via CSV/Excel files
  - Set message templates and delay ranges
  - Evenly distribute leads among accounts

- **Automation**
  - Uses undetected-chromedriver to avoid detection
  - Supports proxy configuration
  - Random delays between messages
  - Real-time progress monitoring

## Requirements

- Python 3.8+
- Chrome/Chromium browser
- Virtual environment (recommended)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd odnoklassniki-outreach-tool
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
# Create .env file
echo "SECRET_KEY=your-secret-key-here" > .env
```

## Usage

1. Start the application:
```bash
python app.py
```

2. Open your browser and navigate to `http://localhost:5000`

3. Add your Odnoklassniki accounts:
   - Go to the Accounts page
   - Fill in account details and proxy settings (if using)
   - Click "Add Account"

4. Create a campaign:
   - Go to the Campaigns page
   - Fill in campaign details
   - Upload your leads file (CSV/Excel with profile URLs)
   - Select accounts to use
   - Set message template and delays
   - Click "Create Campaign"

5. Monitor and manage campaigns:
   - View campaign progress in real-time
   - Start/stop campaigns as needed
   - Check detailed logs for each campaign

## Lead File Format

Your leads file should be either CSV or Excel format with the following structure:

```csv
url
https://ok.ru/profile/123456789
https://ok.ru/profile/987654321
...
```

## Security Considerations

- Store sensitive data (passwords, API keys) in environment variables
- Use proxies to avoid IP bans
- Set reasonable delays between messages
- Monitor account activity for any signs of restrictions

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for educational purposes only. Use it responsibly and in accordance with Odnoklassniki's terms of service. 