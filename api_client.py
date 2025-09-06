
import requests
import json
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

# Get API token from environment variable
API_TOKEN = os.getenv('NUB_YTDLP_API')
BASE_URL = 'http://api.nub-coder.tech'

def get_video_info(url_or_query: str, max_results: int = 1) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[str], Optional[str], Optional[int], Optional[str], Optional[str], str]:
    """Get video info - returns (title, video_id, duration, youtube_link, channel_name, views, stream_url, thumbnail, time_taken)"""
    try:
        response = requests.get(
            f'{BASE_URL}/info',
            params={'token': API_TOKEN, 'q': url_or_query, 'max_results': max_results},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if 'error' in data:
            return None, None, None, None, None, None, None, None, data.get('error', 'Unknown error')
        
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
        logger.error(f"API request failed: {e}")
        return None, None, None, None, None, None, None, None, str(e)

def search_videos(query: str, max_results: int = 5) -> List[Tuple[str, str, str, int, int, str, str]]:
    """Search videos - returns list of (title, video_id, channel_name, duration, views, thumbnail_url, youtube_link)"""
    try:
        response = requests.get(
            f'{BASE_URL}/search',
            params={'q': query, 'max_results': max_results},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if 'error' in data:
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
        return results
    except requests.RequestException as e:
        logger.error(f"API search failed: {e}")
        return []

def get_rate_limit_status() -> Tuple[int, int, int, bool, str]:
    """Get quota status - returns (daily_limit, requests_used, requests_remaining, is_admin, reset_time)"""
    try:
        response = requests.get(
            f'{BASE_URL}/rate-limit-status',
            params={'token': API_TOKEN},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        return (
            data.get('daily_limit', 0),
            data.get('requests_used', 0),
            data.get('requests_remaining', 0),
            data.get('is_admin', False),
            data.get('reset_time', 'N/A')
        )
    except requests.RequestException as e:
        logger.error(f"Rate limit check failed: {e}")
        return 0, 0, 0, False, str(e)
