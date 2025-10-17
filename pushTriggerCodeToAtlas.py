import os
import subprocess
import requests
from requests.auth import HTTPDigestAuth
import time

# --- Configuration ---

# 1. File to watch for changes. When this file is committed, its content will be deployed.
FUNCTION_SOURCE_FILE = 'test.js'
FILES_TO_WATCH = {FUNCTION_SOURCE_FILE}

# 2. Atlas API Configuration - credentials are read from environment variables for security.
ATLAS_GROUP_ID = os.environ.get("ATLAS_GROUP_ID")
ATLAS_PUBLIC_KEY = os.environ.get("ATLAS_PUBLIC_KEY")
ATLAS_PRIVATE_KEY = os.environ.get("ATLAS_PRIVATE_KEY")
# -- NEW: Add these secrets to your GitHub repository --
ATLAS_APP_ID = os.environ.get("ATLAS_APP_ID")
ATLAS_FUNCTION_ID = os.environ.get("ATLAS_FUNCTION_ID")

# --- Helper Functions ---

def get_changed_files():
    """
    Uses Git to find the list of files changed in the most recent commit.
    Returns a set of file paths.
    """
    print("Checking for changed files in the last commit...")
    command = "git diff --name-only HEAD~1 HEAD"
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        changed_files = set(result.stdout.strip().split('\n'))
        print(f"Found changed files: {changed_files}")
        return changed_files
    except subprocess.CalledProcessError as e:
        print(f"Error getting changed files: {e}")
        return set()

def get_bearer_token(username, api_key):
    """Fetches a Bearer token from the Atlas App Services Admin API."""
    print("\nFetching App Services Admin API bearer token...")
    url = 'https://services.cloud.mongodb.com/api/admin/v3.0/auth/providers/mongodb-cloud/login'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    body = {
        'username': username,
        'apiKey': api_key
    }
    try:
        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()  # Raise an exception for bad responses
        token = response.json()['access_token']
        print("Successfully fetched bearer token.")
        return token
    except requests.exceptions.HTTPError as e:
        print(f"Error fetching bearer token: {e.response.status_code}")
        print("Response Body:", e.response.text)
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching token: {e}")
        return None

def call_atlas_api():
    """
    Adds runner IP to access list, then reads a file and updates an Atlas Function.
    """
    if not all([ATLAS_GROUP_ID, ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY, ATLAS_APP_ID, ATLAS_FUNCTION_ID]):
        print("Error: Missing one or more Atlas environment variables (GROUP_ID, PUBLIC_KEY, PRIVATE_KEY, APP_ID, FUNCTION_ID).")
        return

    # --- Step 1: Get the GitHub runner's public IP address ---
    try:
        runner_ip = requests.get('https://api.ipify.org').text
        print(f"Detected CI/CD Runner IP: {runner_ip}")
    except requests.RequestException as e:
        print(f"Could not fetch runner IP: {e}")
        return

    # --- Step 2: Add the runner's IP to the Atlas Access List ---
    print(f"\nAttempting to add IP {runner_ip} to the access list for 1 hour...")
    access_list_endpoint = f"https://cloud.mongodb.com/api/atlas/v2/groups/{ATLAS_GROUP_ID}/accessList"
    access_list_payload = [{"ipAddress": runner_ip, "comment": "Allowing CI/CD Runner for deployment", "deleteAfterDate": "P1H"}]
    access_list_headers = {"Accept": "application/vnd.atlas.2023-01-01+json", "Content-Type": "application/json"}

    try:
        response = requests.post(
            access_list_endpoint, headers=access_list_headers,
            auth=HTTPDigestAuth(ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY), json=access_list_payload
        )
        response.raise_for_status()
        print("Successfully added IP to the access list.")
        print("Waiting 15 seconds for the access list change to apply...")
        time.sleep(15)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 and "IP_ADDRESS_ALREADY_EXISTS" in e.response.text:
            print("IP address is already on the access list. Continuing...")
        else:
            print(f"Error adding IP to access list: {e.response.status_code}\nResponse Body: {e.response.text}")
            return

    # --- Step 3: Get the App Services Admin API Bearer Token ---
    bearer_token = get_bearer_token(ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY)
    if not bearer_token:
        print("Could not retrieve bearer token. Halting execution.")
        return

    # --- Step 4: Read the source code from the file to be deployed ---
    try:
        print(f"\nReading source code from '{FUNCTION_SOURCE_FILE}'...")
        with open(FUNCTION_SOURCE_FILE, 'r') as f:
            function_source_code = f.read()
        print("Successfully read source code.")
    except FileNotFoundError:
        print(f"Error: The source file '{FUNCTION_SOURCE_FILE}' was not found.")
        return
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        return

    # --- Step 5: Update the Atlas Function with the new code ---
    print("\nAttempting to update the Atlas Function...")
    function_endpoint = f"https://services.cloud.mongodb.com/api/admin/v3.0/groups/{ATLAS_GROUP_ID}/apps/{ATLAS_APP_ID}/functions/{ATLAS_FUNCTION_ID}"
    
    function_payload = {"source": function_source_code}
    function_headers = {"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
    
    try:
        response = requests.put(function_endpoint, headers=function_headers, json=function_payload)
        response.raise_for_status()
        print("\nSuccessfully updated Atlas Function!")
        print("API call successful with status code:", response.status_code)
    except requests.exceptions.HTTPError as e:
        print(f"Error calling Atlas Function API: {e.response.status_code}\nResponse Body: {e.response.text}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# --- Main Execution Logic ---
def main():
    """Main function to run the trigger logic."""
    changed_files = get_changed_files()
    if not FILES_TO_WATCH.isdisjoint(changed_files):
        print("\nMonitored file was changed. Triggering Atlas API call...")
        call_atlas_api()
    else:
        print("\nNo monitored files were changed. No action taken.")

if __name__ == "__main__":
    main()

