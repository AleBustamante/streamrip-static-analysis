import asyncio
import logging
import os
import shutil

import aiohttp
from PIL import Image

from ..client import BasicDownloadable
from ..config import ArtworkConfig
from ..metadata import Covers

_artwork_tempdirs: set[str] = set()

logger = logging.getLogger("streamrip")


def remove_artwork_tempdirs():
    logger.debug("Removing dirs %s", _artwork_tempdirs)
    for path in _artwork_tempdirs:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass


async def download_artwork(
    session: aiohttp.ClientSession,
    folder: str,
    covers: Covers,
    config: ArtworkConfig,
    for_playlist: bool,
) -> tuple[str | None, str | None]:
    """Download artwork and update passed Covers object with filepaths."""
    save_artwork = config.save_artwork and not for_playlist
    embed = config.embed

    if not (save_artwork or embed) or covers.empty():
        return None, None

    download_tasks = []
    saved_cover_path = _prepare_saved_cover(session, folder, covers, save_artwork, download_tasks)
    embed_cover_path = _prepare_embed_cover(session, folder, covers, config, embed, download_tasks)

    if download_tasks and not await _perform_downloads(download_tasks):
            return None, None

    _update_covers(covers, config, save_artwork, saved_cover_path, embed, embed_cover_path)

    return embed_cover_path, saved_cover_path


def _prepare_saved_cover(session, folder, covers, save_artwork, download_tasks):
    if not save_artwork:
        return None
    _, l_url, saved_cover_path = covers.largest()
    if saved_cover_path is None and l_url:
        saved_cover_path = os.path.join(folder, "cover.jpg")
        download_tasks.append(_create_download_task(session, l_url, saved_cover_path))
    return saved_cover_path


def _prepare_embed_cover(session, folder, covers, config, embed, download_tasks):
    if not embed:
        return None
    _, embed_url, embed_cover_path = covers.get_size(config.embed_size)
    if embed_cover_path is None and embed_url:
        embed_dir = os.path.join(folder, "__artwork")
        os.makedirs(embed_dir, exist_ok=True)
        _artwork_tempdirs.add(embed_dir)
        embed_cover_path = os.path.join(embed_dir, f"cover{hash(embed_url)}.jpg")
        download_tasks.append(_create_download_task(session, embed_url, embed_cover_path))
    return embed_cover_path


def _create_download_task(session, url, path):
    return BasicDownloadable(session, url, "jpg").download(path, lambda _: None)


async def _perform_downloads(tasks):
    try:
        await asyncio.gather(*tasks)
        return True
    except Exception as e:
        logger.error(f"Error downloading artwork: {e}")
        return False


def _update_covers(covers, config, save_artwork, saved_cover_path, embed, embed_cover_path):
    if save_artwork and saved_cover_path:
        covers.set_largest_path(saved_cover_path)
        if config.saved_max_width > 0:
            downscale_image(saved_cover_path, config.saved_max_width)
    if embed and embed_cover_path:
        covers.set_path(config.embed_size, embed_cover_path)
        if config.embed_max_width > 0:
            downscale_image(embed_cover_path, config.embed_max_width)



def downscale_image(input_image_path: str, max_dimension: int):
    """Downscale an image in place given a maximum allowed dimension.

    Args:
    ----
        input_image_path (str): Path to image
        max_dimension (int): Maximum dimension allowed

    Returns:
    -------


    """
    # Open the image
    image = Image.open(input_image_path)

    # Get the original width and height
    width, height = image.size

    if max_dimension >= max(width, height):
        return

    # Calculate the new dimensions while maintaining the aspect ratio
    if width > height:
        new_width = max_dimension
        new_height = int(height * (max_dimension / width))
    else:
        new_height = max_dimension
        new_width = int(width * (max_dimension / height))

    # Resize the image with the new dimensions
    resized_image = image.resize((new_width, new_height))

    # Save the resized image
    resized_image.save(input_image_path)
