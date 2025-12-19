import pkg_resources
import requests
import subprocess
import sys
import logging
import os
import re
import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from yt_dlp import YoutubeDL
import yt_dlp

logger = logging.getLogger(__name__)

# API Configuration
API_TOKEN = os.getenv('NUB_YTDLP_API')  # from environment variable
BASE_URL = 'http://api.nubcoder.com'

def get_video_info(url_or_query: str, max_results: int = 1) -> Tuple[str, str, int, str, str, int, str, str, str]:
    """Get video info - returns (title, video_id, duration, youtube_link, channel_name, views, stream_url, thumbnail, time_taken)"""
    logger.info(f"Getting video info for: {url_or_query[:50]}{'...' if len(url_or_query) > 50 else ''}")
    try:
        logger.debug(f"Making API request to {BASE_URL}/info with max_results={max_results}")
        response = requests.get(
            f'{BASE_URL}/info',
            params={'token': API_TOKEN, 'q': url_or_query, 'max_results': max_results},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        logger.debug(f"API response status: {response.status_code}")

        if 'error' in data:
            logger.error(f"API returned error: {data.get('error')}")
            return None, None, None, None, None, None, None, None, data.get('error')
        
        logger.info(f"Successfully retrieved video info: {data.get('title', 'N/A')}")
        return (
            data.get('title', 'N/A'),
            data.get('video_id', 'N/A'),
            data.get('duration', 0),
            data.get('youtube_link', 'N/A'),
            data.get('channel_name', 'N/A'),
            data.get('views', 0),
            data.get('url', 'N/A'),
            data.get('thumbnail', 'N/A'),
            data.get('time_taken', 'N/A')
        )
    except requests.RequestException as e:
        logger.error(f"Request failed for video info: {str(e)}")
        return None, None, None, None, None, None, None, None, str(e)

def search_videos(query: str, max_results: int = 5) -> List[Tuple[str, str, str, int, int, str, str]]:
    """Search videos - returns list of (title, video_id, channel_name, duration, views, thumbnail_url, youtube_link)"""
    logger.info(f"Searching videos for query: {query[:50]}{'...' if len(query) > 50 else ''} (max_results={max_results})")
    try:
        logger.debug(f"Making search API request to {BASE_URL}/search")
        response = requests.get(
            f'{BASE_URL}/search',
            params={'q': query, 'max_results': max_results},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        logger.debug(f"Search API response status: {response.status_code}")

        if 'error' in data:
            logger.error(f"Search API returned error: {data.get('error')}")
            return []
        
        results = []
        for video in data.get('results', []):
            results.append((
                video.get('title', 'N/A'),
                video.get('video_id', 'N/A'),
                video.get('channel_name', 'N/A'),
                video.get('duration', 0),
                video.get('views', 0),
                video.get('thumbnail', 'N/A'),
                video.get('youtube_link', 'N/A')
            ))
        logger.info(f"Found {len(results)} video results")
        return results
    except requests.RequestException as e:
        logger.error(f"Search request failed: {str(e)}")
        return []

def get_rate_limit_status() -> Tuple[int, int, int, bool, str]:
    """Get quota status - returns (daily_limit, requests_used, requests_remaining, is_admin, reset_time)"""
    logger.debug("Checking rate limit status")
    try:
        response = requests.get(
            f'{BASE_URL}/rate-limit-status',
            params={'token': API_TOKEN},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        remaining = data.get('requests_remaining', 0)
        used = data.get('requests_used', 0)
        logger.info(f"Rate limit status - Used: {used}, Remaining: {remaining}")

        return (
            data.get('daily_limit', 0),
            data.get('requests_used', 0),
            data.get('requests_remaining', 0),
            data.get('is_admin', False),
            data.get('reset_time', 'N/A')
        )
    except requests.RequestException as e:
        logger.error(f"Failed to get rate limit status: {str(e)}")
        return 0, 0, 0, False, str(e)

def extract_video_id(url):
    """
    Extract YouTube video ID from various forms of YouTube URLs.

    Args:
        url (str): YouTube video URL

    Returns:
        str: Video ID or None if not found
    """
    logger.debug(f"Extracting video ID from URL: {url}")
    try:
        # Patterns for different types of YouTube URLs
        patterns = [
            r'(?:v=|/v/|youtu\.be/|/embed/)([^&?/]+)',  # Standard, shortened and embed URLs
            r'(?:watch\?|/v/|youtu\.be/)([^&?/]+)',     # Watch URLs
            r'(?:youtube\.com/|youtu\.be/)([^&?/]+)'    # Channel URLs
        ]

        # Try each pattern
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                logger.debug(f"Video ID extracted using pattern {i+1}: {video_id}")
                return video_id

        logger.warning(f"No video ID found in URL: {url}")
        return None

    except Exception as e:
        logger.error(f"Error extracting video ID from {url}: {str(e)}")
        return f"Error extracting video ID: {str(e)}"


def format_number(num):
    """Format number to international system (K, M, B). Accepts only digits."""
    if num is None:
        logger.debug("format_number received None, returning N/A")
        return "N/A"

    # If input is a string, check if it's digits only
    if isinstance(num, str):
        if not num.isdigit():
            logger.debug(f"format_number received non-digit string: {num}")
            return "N/A"
        num = int(num)

    # If not int/float after conversion, reject
    if not isinstance(num, (int, float)):
        logger.debug(f"format_number received invalid type: {type(num)}")
        return "N/A"

    if num < 1000:
        return str(num)

    magnitude = 0
    original_num = num
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0

    # Add precision based on magnitude
    if magnitude > 0:
        num = round(num, 1)
        if isinstance(num, float) and num.is_integer():
            num = int(num)

    formatted = f"{num:g}{'KMB'[magnitude-1]}"
    logger.debug(f"Formatted number {original_num} to {formatted}")
    return formatted

def format_duration(seconds):
    """Formats duration from seconds to HH:MM:SS or MM:SS"""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        logger.debug(f"format_duration received invalid input: {seconds} (type: {type(seconds)})")
        return "N/A"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        formatted = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        formatted = f"{minutes:02d}:{secs:02d}"
    
    logger.debug(f"Formatted duration {seconds}s to {formatted}")
    return formatted

def time_to_seconds(time):
    stringt = str(time)
    logger.debug(f"Converting time {stringt} to seconds")
    try:
        seconds = sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))
        logger.debug(f"Converted {stringt} to {seconds} seconds")
        return seconds
    except Exception as e:
        logger.error(f"Error converting time {stringt} to seconds: {str(e)}")
        return 0

def is_ytdlp_updated():
    """Check if yt-dlp is up to date"""
    try:
        # Get installed version
        installed_version = pkg_resources.get_distribution('yt-dlp').version
        
        # Get latest version from PyPI
        response = requests.get('https://pypi.org/pypi/yt-dlp/json', timeout=10)
        latest_version = response.json()['info']['version']
        
        logger.info(f"yt-dlp installed version: {installed_version}")
        logger.info(f"yt-dlp latest version: {latest_version}")
        
        return installed_version == latest_version
    except Exception as e:
        logger.error(f"Error checking yt-dlp version: {e}")
        return False

def update_ytdlp():
    """Update yt-dlp to the latest version"""
    try:
        logger.info("Updating yt-dlp...")
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-U", "yt-dlp"
        ], capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            logger.info("yt-dlp updated successfully!")
            return True
        else:
            logger.error(f"Failed to update yt-dlp: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error updating yt-dlp: {e}")
        return False

async def check_and_update_ytdlp():
    """Check and update yt-dlp if needed"""
    try:
        if not is_ytdlp_updated():
            logger.info("yt-dlp is outdated, updating...")
            if update_ytdlp():
                logger.info("yt-dlp has been updated to the latest version")
            else:
                logger.warning("Failed to update yt-dlp, continuing with current version")
        else:
            logger.info("yt-dlp is already up to date")
    except Exception as e:
        logger.error(f"Error in yt-dlp version check: {e}")

def get_video_details(video_id):
    """
    Get video details using API first, then yt_dlp fallback

    Args:
        video_id (str): Video ID to fetch details for

    Returns:
        dict: Video details or error message
    """
    
    # First try API if token is available
    if API_TOKEN:
        try:
            logger.info("Attempting API request for video details...")
            api_result = get_video_info(video_id)
            
            if api_result and api_result[0] and api_result[0] != "N/A":
                title, video_id_result, duration, youtube_link, channel_name, views, stream_url, thumbnail, time_taken = api_result
                
                # Format duration if it's in seconds
                if isinstance(duration, int):
                    duration = format_duration(duration)
                
                logger.info(f"API request successful, took {time_taken}")
                return {
                    'title': title,
                    'thumbnail': thumbnail,
                    'duration': duration,
                    'view_count': views,
                    'channel_name': channel_name,
                    'video_url': youtube_link,
                    'platform': 'YouTube',
                    'stream_url': stream_url
                }
            else:
                logger.warning("API returned invalid data, falling back to yt-dlp")
        except Exception as e:
            logger.error(f"API request failed: {e}, falling back to yt-dlp")
    else:
        logger.info("No API token found, using yt-dlp")

    # Fallback to yt-dlp
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            "cookiesfrombrowser": ("firefox",),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract initial info using ytsearch
            search_result = ydl.extract_info(f"ytsearch:{video_id}", download=False)

            if not search_result or 'entries' not in search_result or not search_result['entries']:
                return {'error': 'No video found for the given ID'}

            # Get the first entry from search results
            video_info = search_result['entries'][0]

            # Create YouTube URL from video ID
            youtube_url = f"https://www.youtube.com/watch?v={video_info.get('id', video_id)}"

            # Process duration
            duration = 'N/A'
            if video_info.get('duration'):
                try:
                    duration_seconds = int(video_info.get('duration'))
                    duration = format_duration(duration_seconds)
                except (ValueError, TypeError):
                    duration = 'N/A'

            # Get thumbnail URL
            thumbnail = 'N/A'
            if video_info.get('thumbnails'):
                thumbnail = video_info['thumbnails'][-1].get('url', 'N/A')

            # Prepare details dictionary
            details = {
                'title': video_info.get('title', 'N/A'),
                'thumbnail': thumbnail,
                'duration': duration,
                'view_count': video_info.get('view_count', 'N/A'),
                'channel_name': video_info.get('uploader', 'N/A'),
                'video_url': youtube_url,
                'platform': 'YouTube'
            }

            return details

    except (yt_dlp.utils.ExtractorError, yt_dlp.utils.DownloadError) as youtube_error:
        return {'error': f"YouTube extraction failed: {youtube_error}"}
    except Exception as e:
        return {'error': f"Unexpected error: {str(e)}"}

async def handle_youtube_ytdlp(argument):
    """
    Helper function to get YouTube video info using yt-dlp.

    Returns:
        tuple: (title, duration, youtube_link, thumbnail, channel_name, views, video_id)
    """
    try:
        is_url = re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+", argument)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True, # Get basic info without downloading
            'skip_download': True,
            "cookiesfrombrowser": ("firefox",), # Optional: Use cookies from browser
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if is_url:
                 info_dict = ydl.extract_info(argument, download=False)
            else:
               info_dict= ydl.extract_info(f"ytsearch:{argument}", download=False)['entries'][0]

            if not info_dict:
                return None

            title = info_dict.get('title', 'N/A')
            video_id = info_dict.get('id', 'N/A')
            channel_name = info_dict.get('uploader', 'N/A')
            views = info_dict.get('view_count', 'N/A')
            youtube_link = f"https://www.youtube.com/watch?v={video_id}"

            # Duration can be in seconds or a string, convert to seconds if needed
            duration_raw = info_dict.get('duration', 0)
            if isinstance(duration_raw, str):
                try:
                    duration_sec = time_to_seconds(duration_raw)
                except:
                    duration_sec = 0
            else:
                duration_sec = int(duration_raw) if duration_raw else 0
            
            duration_formatted = format_duration(duration_sec)

            thumbnail_url = 'N/A'
            if 'thumbnails' in info_dict and info_dict['thumbnails']:
                 thumbnail_url = info_dict['thumbnails'][-1]['url']


            return (title, duration_formatted, youtube_link, thumbnail_url, channel_name, views, video_id)

    except Exception as e:
        logger.error(f"Error in handle_youtube_ytdlp: {e}")
        return None

async def handle_youtube(argument):
    """
    Main function to get YouTube video information.
    Prioritizes API calls, falls back to yt-dlp.

    Returns:
        tuple: (title, duration, youtube_link, thumbnail, channel_name, views, video_id, stream_url)
    """
    
    # First try API if token is available
    if API_TOKEN:
        try:
            logger.info("Attempting API request for video info...")
            api_result = get_video_info(argument)

            if api_result and api_result[0] and api_result[0] != "N/A":
                title, video_id, duration, youtube_link, channel_name, views, stream_url, thumbnail, time_taken = api_result

                # Format duration if it's in seconds
                if isinstance(duration, int):
                    duration = format_duration(duration)

                logger.info(f"API request successful, took {time_taken}")
                return (title, duration, youtube_link, thumbnail, channel_name, views, video_id, stream_url)
            else:
                logger.warning("API returned invalid data, falling back to yt-dlp")
        except Exception as e:
            logger.error(f"API request failed: {e}, falling back to yt-dlp")
    else:
        logger.info("No API token found, using yt-dlp")

    # Fallback to yt-dlp
    result = await handle_youtube_ytdlp(argument)

    # If yt-dlp fails, return error values
    if not result:
        logger.error("Both API and yt-dlp failed")
        return ("Error", "00:00", None, None, None, None, None, None)

    # Add None for stream_url since yt-dlp doesn't provide it
    return result + (None,)
