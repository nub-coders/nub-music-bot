
import pkg_resources
import requests
import subprocess
import sys
import logging

logger = logging.getLogger(__name__)

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
