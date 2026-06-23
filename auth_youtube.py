import os
import sys
from pathlib import Path

# Add current dir to path for imports
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Error: google-auth-oauthlib is not installed.")
    print("Please run: pip install google-auth-oauthlib google-api-python-client")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

def main():
    client_secrets = BASE_DIR / "config" / "client_secrets.json"
    credentials_out = BASE_DIR / "config" / "youtube_credentials.json"
    
    if not client_secrets.exists():
        print(f"❌ Error: client_secrets.json not found in config/ directory.")
        print(f"Please download your client secrets JSON from Google Cloud Console,")
        print(f"rename it to 'client_secrets.json', and place it in: {client_secrets.parent}")
        sys.exit(1)
        
    print("🔑 Initializing YouTube OAuth flow...")
    print("This will open a browser window to authorize your YouTube channel.")
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
        creds = flow.run_local_server(port=0)
        
        # Write credentials file
        with open(credentials_out, "w") as f:
            f.write(creds.to_json())
            
        print(f"✅ Success! YouTube credentials saved to: {credentials_out}")
        print("You can now transfer this file securely to your VPS.")
    except Exception as e:
        print(f"❌ OAuth Flow Failed: {e}")

if __name__ == "__main__":
    main()
