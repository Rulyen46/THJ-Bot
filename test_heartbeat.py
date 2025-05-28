import requests
import argparse
import os
import sys

def main():
    parser = argparse.ArgumentParser(description='Test heartbeat functionality')
    parser.add_argument('--url', default='http://localhost:80', help='Base URL of the API server')
    parser.add_argument('--token', help='Patcher token for authentication')
    
    args = parser.parse_args()
    
    # Get token from args or environment
    token = args.token or os.getenv('PATCHER_TOKEN')
    if not token:
        print("Warning: No Patcher token provided. Only public endpoints will be accessible.")
    
    # Test basic heartbeat endpoint (no auth needed)
    basic_heartbeat_url = f"{args.url}/heartbeat"
    print(f"\nTesting basic heartbeat endpoint: {basic_heartbeat_url}")
    try:
        response = requests.get(basic_heartbeat_url)
        print(f"HTTP Status: {response.status_code}")
        print(f"Response: {response.json() if response.status_code == 200 else response.text}")
    except Exception as e:
        print(f"Error: {e}")
    
    # If we have a token, test detailed heartbeat
    if token:
        detailed_heartbeat_url = f"{args.url}/heartbeat/detail"
        headers = {"X-Patcher-Token": token}
        print(f"\nTesting detailed heartbeat endpoint: {detailed_heartbeat_url}")
        try:
            response = requests.get(detailed_heartbeat_url, headers=headers)
            print(f"HTTP Status: {response.status_code}")
            print(f"Response: {response.json() if response.status_code == 200 else response.text}")
        except Exception as e:
            print(f"Error: {e}")
    
    # Test Reddit endpoint to verify it still works
    reddit_test_url = f"{args.url}/reddit/test-pin/1kr5l1x?use_test_data=true&test_mode=true"
    if token:
        headers = {"X-Patcher-Token": token}
        print(f"\nTesting Reddit endpoint: {reddit_test_url}")
        try:
            response = requests.get(reddit_test_url, headers=headers)
            print(f"HTTP Status: {response.status_code}")
            print(f"Response: {response.json() if response.status_code == 200 else response.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
