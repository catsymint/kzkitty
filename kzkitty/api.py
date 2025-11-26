import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from xml.etree import ElementTree

from aiohttp import ClientError, ClientSession

from kzkitty.models import Mode

logger = logging.getLogger('kzkitty.api')

class SteamError(Exception):
    pass

class SteamValueError(SteamError):
    pass

class SteamHTTPError(SteamError):
    pass

class SteamXMLError(SteamError):
    pass

class APIError(Exception):
    pass

class APIMapError(APIError):
    pass

@dataclass
class Map:
    name: str
    tier: int
    vnl_tier: int | None
    vnl_pro_tier: int | None
    thumbnail: bytes | None

@dataclass
class PersonalBest:
    player_name: str | None
    map_name: str
    mode: Mode
    time: timedelta
    teleports: int
    points: int
    date: datetime

async def _get_steam_profile(url: str) -> ElementTree.Element:
    try:
        async with ClientSession() as session:
            async with session.get(url) as r:
                if r.status != 200 or r.content_type != 'text/xml':
                    logger.error("Couldn't get Steam profile (HTTP %d)",
                                 r.status)
                    raise SteamHTTPError
                text = await r.text()
    except ClientError:
        logger.exception("Couldn't get Steam profile")
        raise SteamHTTPError

    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError:
        logger.exception("Couldn't parse Steam profile XML")
        raise SteamXMLError

async def steamid64_for_profile(url: str) -> int:
    u = urlparse(url)
    if u.netloc != 'steamcommunity.com':
        raise SteamValueError

    url = f'https://steamcommunity.com{u.path}?xml=1'
    xml = await _get_steam_profile(url)
    steamid64 = xml.find('steamID64')
    if steamid64 is None or steamid64.text is None:
        logger.error('Malformed Steam profile XML (no steamid64)')
        raise SteamXMLError
    try:
        return int(steamid64.text)
    except ValueError:
        logger.exception('Malformed Steam profile XML (bad steamid64)')
        raise SteamXMLError

async def avatar_for_steamid64(steamid64: int) -> bytes:
    url = f'https://steamcommunity.com/profiles/{steamid64}?xml=1'
    xml = await _get_steam_profile(url)
    avatar = xml.find('avatarFull')
    if avatar is None or avatar.text is None:
        logger.error('Malformed Steam profile XML (no avatar)')
        raise SteamXMLError

    try:
        async with ClientSession() as session:
            async with session.get(avatar.text) as r:
                if r.status != 200:
                    logger.error("Couldn't get Steam profile (HTTP %d)",
                                 r.status)
                    raise SteamError
                return await r.content.read()
    except ClientError:
        logger.exception("Couldn't get Steam profile")
        raise SteamError

async def _vnl_tiers_for_map(name: str) -> tuple[int | None, int | None]:
    url = f'https://vnl.kz/api/maps/{name}'
    try:
        async with ClientSession() as session:
            async with session.get(url) as r:
                if r.status != 200:
                    logger.error("Couldn't get vnl.kz map tiers (HTTP %d)",
                                 r.status)
                    return None, None
                json = await r.json()
    except ClientError:
        logger.exception("Couldn't get vnl.kz map tiers")
        return None, None

    if not isinstance(json, dict):
        logger.error("Malformed vnl.kz JSON (not a dict)")
        return None, None
    tp_tier = json.get('tpTier')
    if not isinstance(tp_tier, int):
        logger.error("Malformed vnl.kz JSON (tpTier not an int)")
        tp_tier = None
    pro_tier = json.get('proTier')
    if not isinstance(pro_tier, int):
        logger.error("Malformed vnl.kz JSON (proTier not an int)")
        pro_tier = None
    return tp_tier, pro_tier

async def map_for_name(name: str, mode: Mode) -> Map:
    if not re.fullmatch('[A-za-z0-9_]+', name):
        raise APIMapError

    json = {}
    url = f'https://kztimerglobal.com/api/v2.0/maps/name/{name}'
    try:
        async with ClientSession() as session:
            async with session.get(url) as r:
                if r.status != 200:
                    logger.error("Couldn't get global API map (HTTP %d)",
                                 r.status)
                    raise APIError
                json = await r.json()
    except ClientError:
        logger.exception("Couldn't get global API map")
        raise APIError

    if json is None:
        raise APIMapError
    elif not isinstance(json, dict):
        logger.error('Malformed global API map response (not a dict)')
        raise APIError
    tier = json.get('difficulty')
    if not isinstance(tier, int):
        logger.error('Malformed global API map response (tier not an int)')
        raise APIError

    if mode == Mode.VNL:
        vnl_tier, vnl_pro_tier = await _vnl_tiers_for_map(name)
    else:
        vnl_tier = vnl_pro_tier = None

    thumbnail_url = ('https://raw.githubusercontent.com/KZGlobalTeam/'
                     f'map-images/public/webp/medium/{name}.webp')
    thumbnail = None
    try:
        async with ClientSession() as session:
            async with session.get(thumbnail_url) as r:
                if r.status == 200:
                    thumbnail = await r.content.read()
                else:
                    logger.error("Couldn't get map thumbnail (HTTP %d)",
                                 r.status)
    except ClientError:
        logger.exception("Couldn't get map thumbnail")
        pass

    return Map(name=name, tier=tier, vnl_tier=vnl_tier,
               vnl_pro_tier=vnl_pro_tier, thumbnail=thumbnail)

async def pbs_for_steamid64(steamid64: int, map_name: str, mode: Mode
                            ) -> list[PersonalBest]:
    api_mode = {Mode.KZT: 'kz_timer', Mode.SKZ: 'kz_simple',
                Mode.VNL: 'kz_vanilla'}[mode]
    url = ('https://kztimerglobal.com/api/v2.0/records/top?'
           f'steamid64={steamid64}&map_name={map_name}&stage=0&'
           f'modes_list_string={api_mode}')
    try:
        async with ClientSession() as session:
            async with session.get(url) as r:
                if r.status != 200:
                    logger.error("Couldn't get global API PBs (HTTP %d)",
                                 r.status)
                    raise APIError
                json = await r.json()
    except ClientError:
        logger.exception("Couldn't get global API PBs")
        raise APIError

    if not isinstance(json, list):
        logger.error('Malformed global API PBs (not a list)')
        raise APIError

    pbs = []
    for item in json:
        player_name = item.get('player_name')
        if not isinstance(player_name, str) and player_name is not None:
            logger.error('Malformed global API PB (bad player_name)')
            raise APIError
        time = item.get('time')
        teleports = item.get('teleports')
        points = item.get('points')
        created_on = item.get('created_on')
        if (not isinstance(time, float) or
            not isinstance(teleports, int) or
            not isinstance(points, int) or
            not isinstance(created_on, str)):
            logger.error('Malformed global API PB')
            raise APIError
        try:
            date = datetime.fromisoformat(created_on)
        except ValueError:
            logger.exception('Malformed global API PB (bad date)')
            raise APIError
        date = date.replace(tzinfo=timezone.utc)

        pb = PersonalBest(player_name=player_name, map_name=map_name,
                          time=timedelta(seconds=time), mode=mode,
                          teleports=teleports, points=points, date=date)
        pbs.append(pb)
    return pbs
