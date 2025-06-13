"""
Health Check Script

This script checks the health of the application by making requests to the health endpoints.
It can be run as a standalone script or used in Azure's monitoring system.
"""

import requests
import os
import sys
import json
import argparse
from datetime import datetime

def main():
    """Main entry point for the health check script."""
    
    parser = argparse.ArgumentParser(description='THJ Bot Health Check')
    parser.add_argument('--url', default=os.getenv('HEALTHCHECK_URL', 'http://localhost:80'), 
                        help='Base URL of the API server')
    parser.add_argument('--token', help='Patcher token for authentication')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    parser.add_argument('--output', '-o', choices=['text', 'json'], default='text',
                        help='Output format')
    parser.add_argument('--timeout', '-t', type=int, default=10,
                        help='Request timeout in seconds')
    
    args = parser.parse_args()
    
    # Get token from args or environment
    token = args.token or os.getenv('PATCHER_TOKEN')
    verbose = args.verbose
    
    # Prepare results
    results = {
        "timestamp": datetime.now().isoformat(),
        "checks": []
    }
    success = True
    
    # ==== Check 1: Basic Heartbeat ====
    try:
        response = requests.get(f"{args.url}/heartbeat", timeout=args.timeout)
        status_code = response.status_code
        
        if status_code == 200:
            data = response.json()
            result = {
                "name": "Basic Heartbeat",
                "status": "PASS",
                "details": {
                    "status_code": status_code,
                    "response": data
                }
            }
            if verbose:
                print("✅ Basic Heartbeat: PASS")
                print(f"  Status: {data.get('status')}")
                print(f"  Timestamp: {data.get('timestamp')}")
        else:
            success = False
            result = {
                "name": "Basic Heartbeat",
                "status": "FAIL",
                "details": {
                    "status_code": status_code,
                    "response": response.text
                }
            }
            if verbose:
                print("❌ Basic Heartbeat: FAIL")
                print(f"  Status Code: {status_code}")
                print(f"  Response: {response.text[:100]}...")
        
        results["checks"].append(result)
        
    except Exception as e:
        success = False
        results["checks"].append({
            "name": "Basic Heartbeat",
            "status": "ERROR",
            "details": {"error": str(e)}
        })
        if verbose:
            print(f"❌ Basic Heartbeat: ERROR - {str(e)}")
    
    # ==== Check 2: Detailed Heartbeat (if token available) ====
    if token:
        try:
            headers = {"X-Patcher-Token": token}
            response = requests.get(f"{args.url}/heartbeat/detail", headers=headers, timeout=args.timeout)
            status_code = response.status_code
            
            if status_code == 200:
                data = response.json()
                result = {
                    "name": "Detailed Heartbeat",
                    "status": "PASS",
                    "details": {
                        "status_code": status_code,
                        "system": data.get("system", {}),
                        "environment": data.get("environment", {})
                    }
                }
                if verbose:
                    print("✅ Detailed Heartbeat: PASS")
                    system = data.get("system", {})
                    if "memory_usage_mb" in system:
                        print(f"  Memory: {system['memory_usage_mb']:.1f} MB")
                    if "cpu_percent" in system:
                        print(f"  CPU: {system['cpu_percent']:.1f}%")
                    if "uptime_seconds" in system:
                        uptime = system["uptime_seconds"]
                        hours = int(uptime // 3600)
                        minutes = int((uptime % 3600) // 60)
                        seconds = int(uptime % 60)
                        print(f"  Uptime: {hours}h {minutes}m {seconds}s")
            else:
                result = {
                    "name": "Detailed Heartbeat",
                    "status": "FAIL",
                    "details": {
                        "status_code": status_code,
                        "response": response.text
                    }
                }
                if verbose:
                    print("❌ Detailed Heartbeat: FAIL")
                    print(f"  Status Code: {status_code}")
                    print(f"  Response: {response.text[:100]}...")
            
            results["checks"].append(result)
            
        except Exception as e:
            results["checks"].append({
                "name": "Detailed Heartbeat",
                "status": "ERROR",
                "details": {"error": str(e)}
            })
            if verbose:
                print(f"❌ Detailed Heartbeat: ERROR - {str(e)}")
    elif verbose:
        print("ℹ️ Detailed heartbeat check skipped (no token provided)")
    
    # ==== Check 3: Reddit functionality ====
    if token:
        try:
            headers = {"X-Patcher-Token": token}
            response = requests.get(f"{args.url}/reddit/test-pin/1kr5l1x?use_test_data=true&test_mode=true", 
                                   headers=headers, timeout=args.timeout)
            status_code = response.status_code
            
            if status_code == 200:
                data = response.json()
                result = {
                    "name": "Reddit Integration",
                    "status": "PASS",
                    "details": {
                        "status_code": status_code,
                        "status": data.get("status"),
                        "message": data.get("message")
                    }
                }
                if verbose:
                    print("✅ Reddit Integration: PASS")
                    print(f"  Status: {data.get('status')}")
                    print(f"  Message: {data.get('message')}")
            else:
                success = False
                result = {
                    "name": "Reddit Integration",
                    "status": "FAIL",
                    "details": {
                        "status_code": status_code,
                        "response": response.text
                    }
                }
                if verbose:
                    print("❌ Reddit Integration: FAIL")
                    print(f"  Status Code: {status_code}")
                    print(f"  Response: {response.text[:100]}...")
            
            results["checks"].append(result)
            
        except Exception as e:
            success = False
            results["checks"].append({
                "name": "Reddit Integration",
                "status": "ERROR",
                "details": {"error": str(e)}
            })
            if verbose:
                print(f"❌ Reddit Integration: ERROR - {str(e)}")
    elif verbose:
        print("ℹ️ Reddit integration check skipped (no token provided)")
    
    # Add overall status
    results["overall_status"] = "PASS" if success else "FAIL"
    
    # Output results
    if args.output == 'json':
        print(json.dumps(results, indent=2))
    elif not verbose:
        print(f"Health Check: {'PASS' if success else 'FAIL'}")
        for check in results["checks"]:
            print(f"{check['name']}: {check['status']}")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
