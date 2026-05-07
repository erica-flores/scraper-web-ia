"""Async concurrent image downloader with retry."""

import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config
from models.hotel_data import RoomImage


def sanitize_dirname(name: str) -> str:
    """Convert a room name into a safe directory name.

    Args:
        name: Raw room name string.

    Returns:
        Filesystem-safe lowercase string.
    """
    name = name.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s]+", "_", name)
    return name[:60]


async def download_image(
    session: aiohttp.ClientSession,
    image: RoomImage,
    dest_dir: Path,
) -> RoomImage:
    """Download a single image file.

    Args:
        session: Active aiohttp client session.
        image: RoomImage with url and filename set.
        dest_dir: Directory to save the image.

    Returns:
        Updated RoomImage with local_path set and downloaded=True on success.
    """
    dest_path = dest_dir / image.filename
    try:
        async with session.get(image.url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                content = await resp.read()
                dest_path.write_bytes(content)
                image.local_path = str(dest_path)
                image.downloaded = True
                logger.debug(f"Downloaded: {image.filename}")
            else:
                logger.warning(f"HTTP {resp.status} for {image.url}")
    except Exception as e:
        logger.warning(f"Failed to download {image.url}: {e}")
    return image


async def download_all_images(
    room_images: dict[str, list[RoomImage]],
    output_dir: Path,
) -> dict[str, list[RoomImage]]:
    """Download all images for all rooms concurrently.

    Args:
        room_images: Dict mapping room_name -> list of RoomImage.
        output_dir: Root output directory. Images go in output_dir/images/{room_name}/

    Returns:
        Same dict with updated RoomImage objects (local_path, downloaded).
    """
    semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_IMAGES)
    images_root = output_dir / "images"

    async def bounded_download(session, image, dest):
        async with semaphore:
            return await download_image(session, image, dest)

    async with aiohttp.ClientSession(
        headers={"User-Agent": Config.USER_AGENT}
    ) as session:
        tasks = []
        for room_name, images in room_images.items():
            room_dir = images_root / sanitize_dirname(room_name)
            room_dir.mkdir(parents=True, exist_ok=True)
            for image in images:
                tasks.append(bounded_download(session, image, room_dir))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Rebuild the dict with updated images
    flat_images = [img for imgs in room_images.values() for img in imgs]
    updated = [r for r in results if isinstance(r, RoomImage)]

    # Map back by url
    url_map = {img.url: img for img in updated}
    for room_name, images in room_images.items():
        room_images[room_name] = [url_map.get(img.url, img) for img in images]

    downloaded = sum(1 for img in updated if img.downloaded)
    logger.info(f"Downloaded {downloaded}/{len(flat_images)} images.")
    return room_images
