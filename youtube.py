
import requests
import subprocess
import sys
import os
import re
import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from yt_dlp import YoutubeDL
import yt_dlp
import logging

# API Configuration
API_TOKEN = os.getenv('NUB_YTDLP_API')  # from environment variable
BASE_URL = 'http://api.nubcoder.com'

logger = logging.getLogger(__name__)

def get_video_info(url_or_query: str, max_results: int = 1) -> Tuple[str, str, int, str, str, int, str, str, str]:
    """Get video info - returns (title, video_id, duration, youtube_link, channel_name, views, stream_url, thumbnail, time_taken)"""
    try:
        start_time = time.time()
        logger.debug(
            f"[youtube.get_video_info] Requesting info for query='{url_or_query}' max_results={max_results}; token_set={bool(API_TOKEN)}"
        )
        response = requests.get(
            f'{BASE_URL}/info',
            params={'token': API_TOKEN, 'q': url_or_query, 'max_results': max_results},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        elapsed = round(time.time() - start_time, 3)
        logger.info(f"[youtube.get_video_info] API response received in {elapsed}s")

        if 'error' in data:
            logger.warning(f"[youtube.get_video_info] API returned error: {data.get('error')}")
            return None, None, None, None, None, None, None, None, data.get('error')
        
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
        logger.error(f"[youtube.get_video_info] RequestException: {e}")
        return None, None, None, None, None, None, None, None, str(e)

def search_videos(query: str, max_results: int = 5) -> List[Tuple[str, str, str, int, int, str, str]]:
    """Search videos - returns list of (title, video_id, channel_name, duration, views, thumbnail_url, youtube_link)"""
    try:
        start_time = time.time()
        logger.debug(f"[youtube.search_videos] Searching query='{query}' max_results={max_results}")
        response = requests.get(
            f'{BASE_URL}/search',
            params={'q': query, 'max_results': max_results},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        elapsed = round(time.time() - start_time, 3)
        logger.info(f"[youtube.search_videos] API response received in {elapsed}s")

        if 'error' in data:
            logger.warning(f"[youtube.search_videos] API returned error: {data.get('error')}")
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
        logger.debug(f"[youtube.search_videos] Returning {len(results)} results")
        return results
    except requests.RequestException as e:
        logger.error(f"[youtube.search_videos] RequestException: {e}")
        return []

def get_rate_limit_status() -> Tuple[int, int, int, bool, str]:
    """Get quota status - returns (daily_limit, requests_used, requests_remaining, is_admin, reset_time)"""
    try:
        start_time = time.time()
        logger.debug(f"[youtube.get_rate_limit_status] Requesting rate limit status; token_set={bool(API_TOKEN)}")
        response = requests.get(
            f'{BASE_URL}/rate-limit-status',
            params={'token': API_TOKEN},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        elapsed = round(time.time() - start_time, 3)
        logger.info(f"[youtube.get_rate_limit_status] API response received in {elapsed}s")
        
        remaining = data.get('requests_remaining', 0)
        used = data.get('requests_used', 0)

        status = (
            data.get('daily_limit', 0),
            data.get('requests_used', 0),
            data.get('requests_remaining', 0),
            data.get('is_admin', False),
            data.get('reset_time', 'N/A')
        )
        logger.debug(f"[youtube.get_rate_limit_status] Parsed status: {status}")
        return status
    except requests.RequestException as e:
        logger.error(f"[youtube.get_rate_limit_status] RequestException: {e}")
        return 0, 0, 0, False, str(e)

def extract_video_id(url):
    """
    Extract YouTube video ID from various forms of YouTube URLs.

    Args:
        url (str): YouTube video URL

    Returns:
        str: Video ID or None if not found
    """
    try:
        logger.debug(f"[youtube.extract_video_id] Extracting video id from url='{url}'")
        # Patterns for different types of YouTube URLs
        patterns = [
            r'(?:v=|/v/|youtu\.be/|/embed/)([^&?/]+)',  # Standard, shortened and embed URLs
            r'(?:watch\?|/v/|youtu\.be/)([^&?/]+)',     # Watch URLs
            r'(?:youtube\.com/|youtu\.be/)([^&?/]+)'    # Channel URLs
        ]

        # Try each pattern
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                logger.debug(f"[youtube.extract_video_id] Matched pattern '{pattern}', video_id='{video_id}'")
                return video_id

        logger.debug("[youtube.extract_video_id] No match found")
        return None

    except Exception as e:
        logger.error(f"[youtube.extract_video_id] Error: {e}")
        return f"Error extracting video ID: {str(e)}"


def format_number(num):
    """Format number to international system (K, M, B). Accepts only digits."""
    if num is None:
        logger.debug("[youtube.format_number] Input is None")
        return "N/A"

    # If input is a string, check if it's digits only
    if isinstance(num, str):
        if not num.isdigit():
            logger.debug(f"[youtube.format_number] Non-digit string input: {num}")
            return "N/A"
        num = int(num)

    # If not int/float after conversion, reject
    if not isinstance(num, (int, float)):
        logger.debug(f"[youtube.format_number] Invalid type: {type(num).__name__}")
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
    logger.debug(f"[youtube.format_number] Formatted {original_num} -> {formatted}")
    return formatted

def format_duration(seconds):
    """Formats duration from seconds to HH:MM:SS or MM:SS"""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        logger.debug(f"[youtube.format_duration] Invalid seconds input: {seconds}")
        return "N/A"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        formatted = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        formatted = f"{minutes:02d}:{secs:02d}"
    
    return formatted

def time_to_seconds(time):
    stringt = str(time)
    try:
        seconds = sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))
        logger.debug(f"[youtube.time_to_seconds] Converted '{time}' -> {seconds}s")
        return seconds
    except Exception as e:
        logger.warning(f"[youtube.time_to_seconds] Failed to convert '{time}': {e}")
        return 0

def is_ytdlp_updated():
    """Check if yt-dlp is up to date"""
    try:
        # Get installed version using modern API
        try:
            from importlib.metadata import version, PackageNotFoundError
            installed_version = version('yt-dlp')
        except PackageNotFoundError:
            logger.warning("[youtube.is_ytdlp_updated] yt-dlp not installed via pip")
            return False
        
        # Get latest version from PyPI
        response = requests.get('https://pypi.org/pypi/yt-dlp/json', timeout=10)
        response.raise_for_status()  # better error handling
        latest_version = response.json()['info']['version']
        
        is_current = installed_version == latest_version
        logger.info(
            f"[youtube.is_ytdlp_updated] Installed={installed_version}, "
            f"Latest={latest_version}, UpToDate={is_current}"
        )
        return is_current
    
    except requests.RequestException as e:
        logger.error(f"[youtube.is_ytdlp_updated] PyPI request failed: {e}")
        return False
    except Exception as e:
        logger.error(f"[youtube.is_ytdlp_updated] Error: {e}")
        return False

def update_ytdlp():
    """Update yt-dlp to the latest version"""
    try:
        logger.info("[youtube.update_ytdlp] Updating yt-dlp")
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-U", "yt-dlp"
        ], capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            logger.info("[youtube.update_ytdlp] Update successful")
            return True
        else:
            logger.error(f"[youtube.update_ytdlp] Update failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"[youtube.update_ytdlp] Error: {e}")
        return False

async def check_and_update_ytdlp():
    """Check and update yt-dlp if needed"""
    try:
        logger.debug("[youtube.check_and_update_ytdlp] Checking yt-dlp status")
        if not is_ytdlp_updated():
            logger.info("[youtube.check_and_update_ytdlp] yt-dlp is outdated, updating")
            update_ytdlp()
        else:
            logger.info("[youtube.check_and_update_ytdlp] yt-dlp is up to date")
    except Exception as e:
        logger.error(f"[youtube.check_and_update_ytdlp] Error: {e}")

def extract_best_format(formats):
    """Pick the best format (progressive MP4 preferred) and return URL"""
    if not formats:
        logger.debug("[youtube.extract_best_format] No formats provided")
        return 'N/A'

    def has_av_and_http(f):
        return (
            f.get("acodec") != "none"
            and f.get("vcodec") != "none"
            and str(f.get("protocol", "")).startswith("http")
            and f.get("url")
        )

    # Prefer progressive MP4 (most universally playable)
    for f in formats:
        if has_av_and_http(f) and f.get("ext") == "mp4":
            logger.debug("[youtube.extract_best_format] Selected progressive MP4 format")
            return f.get("url", 'N/A')

    # Next: any HTTP progressive (audio+video)
    for f in formats:
        if has_av_and_http(f):
            logger.debug("[youtube.extract_best_format] Selected progressive AV format")
            return f.get("url", 'N/A')

    # Fallback: first available URL
    for f in formats:
        if f.get("url"):
            logger.debug("[youtube.extract_best_format] Selected fallback format with URL")
            return f.get("url", 'N/A')

    return 'N/A'

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
            logger.debug(f"[youtube.get_video_details] Using API for video_id='{video_id}'")
            api_result = get_video_info(video_id)
            
            if api_result and api_result[0] and api_result[0] != "N/A":
                title, video_id_result, duration, youtube_link, channel_name, views, stream_url, thumbnail, time_taken = api_result
                
                # Format duration if it's in seconds
                if isinstance(duration, int):
                    duration = format_duration(duration)
                
                return {
                    'title': title,
                    'thumbnail': thumbnail,
                    'duration': duration,
                    'view_count': views,
                    'channel_name': channel_name,
                    'video_url': youtube_link,
                    'platform': 'YouTube',
                    'stream_url': stream_url,
                    'video_id': video_id_result
                }
            else:
                logger.warning("[youtube.get_video_details] API returned no usable data, falling back to yt-dlp")
        except Exception as e:
            logger.error(f"[youtube.get_video_details] API error: {e}")

    # Fallback to yt-dlp
    try:
        logger.debug(f"[youtube.get_video_details] Using yt-dlp fallback for video_id='{video_id}'")
        ydl_opts = {
            # Only gather metadata, no downloads
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "cookiesfrombrowser": ("firefox",),
            "format": "best",

            # Performance optimizations
            "extract_flat": False,  # We need full info
            "writethumbnail": False,
            "writeinfojson": False,
            "writedescription": False,
            "writesubtitles": False,
            "writeautomaticsub": False,

            # Network optimizations  
            "http_chunk_size": 10485760,  # 10MB chunks
            "retries": 1,  # Reduce retries for speed
            "fragment_retries": 1,

            # Skip unnecessary processing
            "skip_playlist_after_errors": 1,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract initial info using ytsearch
            search_result = ydl.extract_info(f"ytsearch:{video_id}", download=False)

            if not search_result or 'entries' not in search_result or not search_result['entries']:
                logger.warning("[youtube.get_video_details] No entries found in yt-dlp search")
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

            # Extract best format stream URL
            stream_url = extract_best_format(video_info.get('formats', []))

            # Prepare details dictionary
            details = {
                'title': video_info.get('title', 'N/A'),
                'thumbnail': thumbnail,
                'duration': duration,
                'view_count': video_info.get('view_count', 'N/A'),
                'channel_name': video_info.get('uploader', 'N/A'),
                'video_url': youtube_url,
                'platform': 'YouTube',
                'stream_url': stream_url,
                'video_id': video_info.get('id', video_id)
            }

            logger.info(f"[youtube.get_video_details] yt-dlp details extracted for id='{details.get('video_id')}'")
            return details

    except (yt_dlp.utils.ExtractorError, yt_dlp.utils.DownloadError) as youtube_error:
        logger.error(f"[youtube.get_video_details] YouTube extraction failed: {youtube_error}")
        return {'error': f"YouTube extraction failed: {youtube_error}"}
    except Exception as e:
        logger.error(f"[youtube.get_video_details] Unexpected error: {e}")
        return {'error': f"Unexpected error: {str(e)}"}

async def handle_youtube_ytdlp(argument):
    """
    Helper function to get YouTube video info using yt-dlp.

    Returns:
        tuple: (title, duration, youtube_link, thumbnail, channel_name, views, video_id, stream_url)
    """
    try:
        is_url = re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+", argument)
        logger.debug(f"[youtube.handle_youtube_ytdlp] argument='{argument}', is_url={bool(is_url)}")
        ydl_opts = {
            # Only gather metadata, no downloads
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "cookiesfrombrowser": ("firefox",),
            "format": "best",

            # Performance optimizations
            "extract_flat": False,
            "writethumbnail": False,
            "writeinfojson": False,
            "writedescription": False,
            "writesubtitles": False,
            "writeautomaticsub": False,

            # Network optimizations  
            "http_chunk_size": 10485760,  # 10MB chunks
            "retries": 1,  # Reduce retries for speed
            "fragment_retries": 1,

            # Skip unnecessary processing
            "skip_playlist_after_errors": 1,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if is_url:
                 info_dict = ydl.extract_info(argument, download=False)
            else:
               info_dict= ydl.extract_info(f"ytsearch:{argument}", download=False)['entries'][0]

            if not info_dict:
                logger.warning("[youtube.handle_youtube_ytdlp] No info_dict returned")
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

            # Extract stream URL from formats
            stream_url = 'N/A'
            if 'formats' in info_dict and info_dict['formats']:
                # Get the best format with audio and video, or best available
                for fmt in reversed(info_dict['formats']):
                    if fmt.get('url'):
                        stream_url = fmt.get('url', 'N/A')
                        break

            logger.info(f"[youtube.handle_youtube_ytdlp] Extracted info for id='{video_id}', title='{title}'")

            return (title, duration_formatted, youtube_link, thumbnail_url, channel_name, views, video_id, stream_url)

    except Exception as e:
        logger.error(f"[youtube.handle_youtube_ytdlp] Error: {e}")
        return None

async def handle_youtube(argument):
    """
    Main function to get YouTube video information.
    Prioritizes API calls, falls back to yt-dlp via get_video_details.

    Returns:
        tuple: (title, duration, youtube_link, thumbnail, channel_name, views, video_id, stream_url)
    """
    
    # Use get_video_details which handles API → yt-dlp fallback
    logger.debug(f"[youtube.handle_youtube] Handling argument='{argument}'")
    details = get_video_details(argument)
    
    if 'error' in details:
        logger.warning(f"[youtube.handle_youtube] Failed to get details: {details.get('error')}")
        return ("Error", "00:00", None, None, None, None, None, None)
    
    # Convert dict result to tuple format
    result_tuple = (
        details.get('title', 'N/A'),
        details.get('duration', 'N/A'),
        details.get('video_url', 'N/A'),
        details.get('thumbnail', 'N/A'),
        details.get('channel_name', 'N/A'),
        details.get('view_count', 'N/A'),
        details.get('video_id', 'N/A'),
        details.get('stream_url', 'N/A')
    )

    logger.info(f"[youtube.handle_youtube] Success: title='{details.get('title', 'N/A')}', id='{details.get('video_id', 'N/A')}'")
    return result_tuple
