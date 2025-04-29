#!/usr/bin/env python3
"""
42 Logtime Data Fetcher and GitHub Gist Creator for Scriptable Widget
Fetches logtime data from the 42 API, creates a compatible JSON structure, 
and updates a GitHub Gist to be used with the Scriptable widget.
Includes current session tracking for real-time logtime updates.
"""

import os
import json
import requests
from datetime import datetime, timedelta, date
import calendar
import pytz  # For proper timezone handling

# Configuration
API_URL = "https://api.intra.42.fr"
USERNAME = os.environ.get("FT_USERNAME", "aelomari")  # Set your default username
GIST_DESCRIPTION = f"42 Logtime Data for {USERNAME} (Scriptable Widget)"
GIST_FILENAME = "logtime.json"
TIMEZONE = "Europe/Paris"  # Change to your campus timezone

def get_access_token():
    """Get an OAuth access token from the 42 API"""
    client_id = os.environ.get("FT_CLIENT_ID")
    client_secret = os.environ.get("FT_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise ValueError("FT_CLIENT_ID and FT_CLIENT_SECRET environment variables must be set")
    
    response = requests.post(
        f"{API_URL}/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret
        }
    )
    
    response.raise_for_status()
    return response.json()["access_token"]

def get_user_data(token):
    """Get user data from the 42 API"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_URL}/v2/users/{USERNAME}", headers=headers)
    response.raise_for_status()
    return response.json()

def get_logtime_data(token):
    """Get logtime data from the 42 API"""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get locations (logtimes) for the past 90 days to calculate monthly data
    end_date = datetime.now(pytz.timezone(TIMEZONE))
    start_date = end_date - timedelta(days=90)
    
    response = requests.get(
        f"{API_URL}/v2/users/{USERNAME}/locations",
        headers=headers,
        params={
            "range[begin_at]": f"{start_date.isoformat()},{end_date.isoformat()}",
            "page[size]": 100,
            "sort": "-begin_at"
        }
    )
    
    response.raise_for_status()
    return response.json()

def get_user_location(token, location_id):
    """Get more detailed information about a specific location"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_URL}/v2/locations/{location_id}", headers=headers)
    response.raise_for_status()
    return response.json()

def get_current_session(token):
    """Check if the user is currently logged in and calculate session time"""
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get the most recent location data
    response = requests.get(
        f"{API_URL}/v2/users/{USERNAME}/locations",
        headers=headers,
        params={
            "page[size]": 1,
            "sort": "-begin_at"
        }
    )
    
    response.raise_for_status()
    locations = response.json()
    
    if not locations:
        return None
    
    latest = locations[0]
    begin_at = datetime.fromisoformat(latest["begin_at"].replace("Z", "+00:00"))
    
    # If end_at is null, the user is currently logged in
    if latest["end_at"] is None:
        # Calculate current session duration
        current_time = datetime.now(pytz.timezone("UTC"))
        duration_hours = (current_time - begin_at).total_seconds() / 3600
        
        # Get more detailed location information
        location_info = get_user_location(token, latest["id"])
        host = latest.get("host", "Unknown")
        
        # Try to get a better location description - looking for campus and cluster info
        campus = None
        cluster = None
        
        if "campus" in location_info:
            campus = location_info["campus"]["name"]
        
        if "host" in location_info and location_info["host"]:
            host_parts = location_info["host"].split('.')
            if len(host_parts) > 0:
                cluster = host_parts[0]
        
        # Create a descriptive location string
        location = f"{campus} - {cluster}" if campus and cluster else host
        
        return {
            "begin_at": begin_at.isoformat(),
            "duration_hours": round(duration_hours, 2),
            "location": location
        }
    
    return None

def calculate_hours(locations):
    """Calculate daily and monthly hour totals from location data"""
    daily_hours = {}
    monthly_hours = {}
    
    now = datetime.now(pytz.timezone("UTC"))
    today = now.strftime("%Y-%m-%d")
    
    for loc in locations:
        begin_at = datetime.fromisoformat(loc["begin_at"].replace("Z", "+00:00"))
        end_at = datetime.fromisoformat(loc["end_at"].replace("Z", "+00:00")) if loc["end_at"] else now
        
        # Calculate duration in hours
        duration = (end_at - begin_at).total_seconds() / 3600
        
        # Add to daily totals
        day_key = begin_at.strftime("%Y-%m-%d")
        if day_key not in daily_hours:
            daily_hours[day_key] = 0
        daily_hours[day_key] += duration
        
        # Add to monthly totals
        month_key = begin_at.strftime("%Y-%m")
        if month_key not in monthly_hours:
            monthly_hours[month_key] = 0
        monthly_hours[month_key] += duration
    
    # Round values
    for key in daily_hours:
        daily_hours[key] = round(daily_hours[key], 2)
    
    for key in monthly_hours:
        monthly_hours[key] = round(monthly_hours[key], 2)
    
    return daily_hours, monthly_hours

def create_or_update_gist(data):
    """Create or update a GitHub Gist with the logtime data in JSON format"""
    github_token = os.environ.get("GH_TOKEN")
    if not github_token:
        raise ValueError("GH_TOKEN environment variable must be set")
    
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Serialize to JSON string with indentation for readability
    json_content = json.dumps(data, indent=2)
    
    # Check if gist already exists
    gist_id = os.environ.get("GIST_ID")
    
    if gist_id:
        # Update existing gist
        url = f"https://api.github.com/gists/{gist_id}"
        payload = {
            "description": GIST_DESCRIPTION,
            "files": {
                GIST_FILENAME: {
                    "content": json_content
                }
            }
        }
        response = requests.patch(url, headers=headers, json=payload)
    else:
        # Create new gist
        url = "https://api.github.com/gists"
        payload = {
            "description": GIST_DESCRIPTION,
            "public": True,
            "files": {
                GIST_FILENAME: {
                    "content": json_content
                }
            }
        }
        response = requests.post(url, headers=headers, json=payload)
    
    response.raise_for_status()
    result = response.json()
    
    # Get the raw URL for the JSON file
    raw_url = result["files"][GIST_FILENAME]["raw_url"]
    
    return result["html_url"], result["id"], raw_url

def format_time_difference(start_time_str):
    """Calculate and format the difference between a start time and now"""
    try:
        start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        now = datetime.now(pytz.timezone("UTC"))
        
        # Calculate time difference
        diff = now - start_time
        hours = int(diff.total_seconds() // 3600)
        minutes = int((diff.total_seconds() % 3600) // 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    except Exception as e:
        return "Error calculating time"

def main():
    """Main function"""
    try:
        # Get OAuth token
        token = get_access_token()
        
        # Get user data
        user_data = get_user_data(token)
        
        # Get logtime data
        locations = get_logtime_data(token)
        
        # Calculate hours
        daily_hours, monthly_hours = calculate_hours(locations)
        
        # Check for current active session
        current_session = get_current_session(token)
        
        # Calculate totals
        total_hours = sum(daily_hours.values())
        
        # Calculate recent daily total (last 7 days)
        now = datetime.now()
        recent_days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
        recent_daily_total = sum(daily_hours.get(day, 0) for day in recent_days)
        
        # Create output data structure - matching exactly what the Scriptable widget expects
        output_data = {
            "username": USERNAME,
            "total_hours": round(total_hours, 2),
            "recent_daily_total": round(recent_daily_total, 2),
            "daily_hours": daily_hours,
            "monthly_hours": monthly_hours,
            "updated_at": datetime.now().isoformat(),
            "current_session": current_session  # Add current session data
        }
        
        # Create or update GitHub Gist
        gist_url, gist_id, raw_url = create_or_update_gist(output_data)
        
        print(f"Successfully updated logtime data for {USERNAME}")
        print(f"Gist URL: {gist_url}")
        print(f"Gist ID: {gist_id}")
        print(f"Raw JSON URL (for Scriptable): {raw_url}")
        
        if current_session:
            print(f"\nCurrent active session:")
            print(f"Started at: {current_session['begin_at']}")
            print(f"Duration: {current_session['duration_hours']} hours")
            print(f"Location: {current_session['location']}")
            
            # Calculate and show time difference
            start_time_str = "2025-04-25T20:34:59+00:00"  # Your specific start time
            time_diff = format_time_difference(start_time_str)
            print(f"Time since {start_time_str}: {time_diff}")
        
        print("\nSetup instructions:")
        print("1. Set this Gist ID as the GIST_ID environment variable for future updates")
        print("2. In your Scriptable widget, update the DATA_URL to:")
        print(f"   const DATA_URL = \"{raw_url}\";")
        print(f"3. Set DEFAULT_USERNAME to: \"{USERNAME}\"")
        
    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()