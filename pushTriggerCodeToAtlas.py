import os
import subprocess
import requests
from requests_toolbelt.auth.mongodb import MongoDigestAuth

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

    # --- CUSTOMIZE YOUR API CALL HERE ---
    # This example updates the IP Access List for your project.
    # You will need to change the endpoint and payload for your specific needs.
    
    # 1. Define the API endpoint
    endpoint = f"https://cloud.mongodb.com/api/atlas/v2/groups/{ATLAS_GROUP_ID}/clusters"
    
    # 2. Create the JSON payload for the request
    # This payload adds the IP of the GitHub runner for 1 hour.
    # We get the runner's IP from a trusted service.
    try:
        runner_ip = requests.get('https://api.ipify.org').text
        print(f"Detected CI/CD Runner IP: {runner_ip}")
    except requests.RequestException as e:
        print(f"Could not fetch runner IP: {e}")
        return

    #payload = [
    #    {
    #        "ipAddress": runner_ip,
    #        "comment": "Allowing CI/CD Runner for deployment",
    #        "deleteAfterDate": "P1H" # ISO 8601 duration format for 1 hour
    #    }
    #]
    
    # 3. Set up the authentication and headers
    auth = MongoDigestAuth(ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY)
    headers = {"Accept": "application/vnd.atlas.2023-01-01+json"}

    print(f"Calling Atlas API endpoint: {endpoint}")
    try:
        response = requests.post(endpoint, auth=auth, headers=headers)
        response.raise_for_status()  # This will raise an exception for HTTP error codes (4xx or 5xx)
        
        print("Successfully called Atlas Admin API!")
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

    # Check if any of the changed files are in our watch list
    if not FILES_TO_WATCH.isdisjoint(changed_files):
        print("\nMonitored file was changed. Triggering Atlas API call...")
        call_atlas_api()
    else:
        print("\nNo monitored files were changed. No action taken.")

if __name__ == "__main__":
    main()
