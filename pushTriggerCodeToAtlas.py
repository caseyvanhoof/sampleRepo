import os
import subprocess
import requests
from requests.auth import HTTPDigestAuth
import time

# --- Configuration ---

# 1. Files to watch for changes. If any of these files are in a commit, the API will be called.
#    Update this list with the files you care about.
FILES_TO_WATCH = {
    'test.py',
}

# 2. Atlas API Configuration - credentials are read from environment variables for security.
ATLAS_GROUP_ID = os.environ.get("ATLAS_GROUP_ID")
ATLAS_PUBLIC_KEY = os.environ.get("ATLAS_PUBLIC_KEY")
ATLAS_PRIVATE_KEY = os.environ.get("ATLAS_PRIVATE_KEY")

# --- Helper Functions ---

def get_changed_files():
    """
    Uses Git to find the list of files changed in the most recent commit.
    Returns a set of file paths.
    """
    print("Checking for changed files in the last commit...")
    # This command compares the latest commit (HEAD) with the one before it (HEAD~1)
    command = "git diff --name-only HEAD~1 HEAD"
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        changed_files = set(result.stdout.strip().split('\n'))
        print(f"Found changed files: {changed_files}")
        return changed_files
    except subprocess.CalledProcessError as e:
        print(f"Error getting changed files: {e}")
        return set()

def call_atlas_api():
    """
    Constructs and sends a request to a specific Atlas Admin API endpoint.
    """
    if not all([ATLAS_GROUP_ID, ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY]):
        print("Error: Missing one or more Atlas environment variables (GROUP_ID, PUBLIC_KEY, PRIVATE_KEY).")
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
    
    # This payload adds the IP with a comment and sets it to auto-delete after 1 hour.
    access_list_payload = [
        {
            "ipAddress": runner_ip,
            "comment": "Allowing CI/CD Runner for deployment",
            "deleteAfterDate": "P1H" # ISO 8601 duration format for 1 hour
        }
    ]
    
    access_list_headers = {
        "Accept": "application/vnd.atlas.2023-01-01+json",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            access_list_endpoint,
            headers=access_list_headers,
            auth=HTTPDigestAuth(ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY),
            json=access_list_payload
        )
        response.raise_for_status()
        print("Successfully added IP to the access list.")
        # It can take a moment for the access list change to propagate.
        print("Waiting 15 seconds for the access list change to apply...")
        time.sleep(15)

    except requests.exceptions.HTTPError as e:
        # If the IP is already on the list, Atlas returns a 400 error. We can safely ignore it.
        if e.response.status_code == 400 and "IP_ADDRESS_ALREADY_EXISTS" in e.response.text:
            print("IP address is already on the access list. Continuing...")
        else:
            print(f"Error adding IP to access list: {e.response.status_code}")
            print("Response Body:", e.response.text)
            return # Stop execution if we can't add the IP

    # --- Step 3: Proceed with the original API call to list clusters ---
    print("\nProceeding to list clusters...")
    clusters_endpoint = f"https://cloud.mongodb.com/api/atlas/v2/groups/{ATLAS_GROUP_ID}/clusters"
    
    clusters_headers = {  
        "Accept": "application/vnd.atlas.2023-01-01+json"
    }

    print(f"Calling Atlas API endpoint: {clusters_endpoint}")
    try:
        response = requests.get(  
            clusters_endpoint,  
            headers=clusters_headers,  
            auth=HTTPDigestAuth(ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY)
        )          
        response.raise_for_status()
        
        print("\nSuccessfully called Atlas Admin API!")
        print("Response:", response.json())

    except requests.exceptions.HTTPError as e:
        print(f"Error calling Atlas API: {e.response.status_code}")
        print("Response Body:", e.response.text)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# --- Main Execution Logic ---

def main():
    """
    Main function to run the trigger logic.
    """
    changed_files = get_changed_files()

    if not FILES_TO_WATCH.isdisjoint(changed_files):
        print("\nMonitored file was changed. Triggering Atlas API call...")
        call_atlas_api()
    else:
        print("\nNo monitored files were changed. No action taken.")

if __name__ == "__main__":
    main()

