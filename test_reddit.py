import os
import sys
import json
import requests
import argparse
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description='Test Reddit posting functionality')
    parser.add_argument('--url', default='http://localhost:80', help='Base URL of the API server')
    parser.add_argument('--token', help='Patcher token for authentication')
    parser.add_argument('--live', action='store_true', help='Run in live mode (actually post to Reddit)')
    parser.add_argument('--real-data', action='store_true', help='Use real changelog data instead of test data')
    parser.add_argument('--entry-id', help='Specific changelog entry ID to test with')
    
    args = parser.parse_args()
    
    # Get token from args or environment
    token = args.token or os.getenv('PATCHER_TOKEN')
    if not token:
        sys.exit("Error: Patcher token not provided. Use --token or set PATCHER_TOKEN environment variable.")
    
    # Prepare the request
    url = f"{args.url}/reddit/test"
    headers = {
        'X-Patcher-Token': token,
        'Content-Type': 'application/json'
    }
    
    payload = {
        'test_mode': not args.live,
        'use_real_data': args.real_data
    }
    
    if args.entry_id:
        payload['entry_id'] = args.entry_id
    
    # Print test configuration
    print("\n===== REDDIT POSTING TEST =====")
    print(f"API URL: {url}")
    print(f"Mode: {'LIVE - Will post to Reddit' if args.live else 'SIMULATION - No actual posts'}")
    print(f"Data: {'Real changelog data' if args.real_data else 'Test mock data'}")
    if args.entry_id:
        print(f"Entry ID: {args.entry_id}")
    print("===============================\n")
    
    try:
        # Send the request
        response = requests.post(url, headers=headers, json=payload)
        
        # Process the response
        if response.status_code == 200:
            result = response.json()
            print(f"Test Status: {result['status']}")
            print(f"Message: {result['message']}")
            
            if 'test_details' in result:
                details = result['test_details']
                print("\n---- Test Details ----")
                print(f"Mode: {details['mode']}")
                print(f"Entry ID: {details['entry_id']}")
                
                if details['mode'] == "simulation":
                    print(f"Would Post To: r/{details['would_post_to_subreddit']}")
                    print(f"Post Title: {details['post_title']}")
                    print("\nFormatted Content Preview:")
                    print("-------------------------")
                    print(details['formatted_content'][:500] + "..." if len(details['formatted_content']) > 500 else details['formatted_content'])
                    print("-------------------------")
                    print(f"Reddit Credentials Configured: {'Yes' if details['reddit_credentials_configured'] else 'No - Configure before going live'}")
                else:
                    print(f"Posted To: r/{details['posted_to_subreddit']}")
        else:
            print(f"Error: HTTP {response.status_code}")
            print(response.text)
    
    except requests.RequestException as e:
        print(f"Connection error: {str(e)}")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    main()