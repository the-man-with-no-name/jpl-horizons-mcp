import httpx
from mcp.server.fastmcp import FastMCP
from typing import Any, Optional, Tuple
from enum import StrEnum, auto
from dataclasses import dataclass

### HORIZONS API FOR LOCATIONS

JPL_HORIZONS_BASE_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

class UpperStrEnum(StrEnum):
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return name.upper()

class Ephemeris(UpperStrEnum):
    OBSERVER = auto()
    VECTORS = auto()
    ELEMENTS = auto()
    SPK = auto()
    APPROACH = auto()

class CenterEnum(UpperStrEnum):
    COORD = auto()
    GEO = auto()

class CoordTypeEnum(UpperStrEnum):
    GEODETIC = auto()
    CYLINDRICAL = auto()

class CaTableTypeEnum(UpperStrEnum):
    STANDARD = auto()
    EXTENDED = auto()

class EphemDataBase:
    pass

@dataclass
class Observer(EphemDataBase):
    Center: CenterEnum
    CoordType: CoordTypeEnum
    SiteCoord: Tuple[float, float, float]
    StartTime: str
    StopTime: str

@dataclass
class Vectors(EphemDataBase):
    Center: CenterEnum

@dataclass
class Elements(EphemDataBase):
    Center: CenterEnum

@dataclass
class Spk(EphemDataBase):
    StartTime: str
    StopTime: str

@dataclass
class Approach(EphemDataBase):
    CaTableType: CaTableTypeEnum
    Tca3sgLimit: int = 14400
    CalimSb: float = 0.05
    CalimPl: Tuple[float, float, float, float, float, float, float, float, float, float] = (0.1, 0.1, 0.1, 0.1, 1.0, 1.0, 1.0, 1.0, 0.1, 0.003)

mcp = FastMCP("jpl-horizons-mcp-server")

async def _make_request(
    url: str,
    command: str,
    obj_data: bool,
    make_ephem: bool,
    ephem_type: Ephemeris,
    ephem_data: EphemDataBase
) -> dict[str, Any] | None:
    """
    Access the JPL Horizons system. The Horizons system is an ephemeris system
    providing acccess to solar system data and customizable production of 
    accurate ephemerides for observers, mission-planners, researchers, and the 
    public, by numerically characterizing the location, motion, and
    observability of solar system objects as a function of time, as seen from
    locations within the solar system.

    Arguments:
        command: name or id of the target body
        obj_data: toggles return of object summary data
        make_ephem: togges generation of ephemeris, if possible
        ephem_type: selects type of ephemeris to generate
    """
    
    # Build the query parameters
    query_params = {
        format: "json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

@mcp.tool()
async def observer_request(
    command: str,
    obj_data: bool,
    make_ephem: bool,
    observer_data: Observer
) -> dict[str, Any] | None:
    """
    Description here
    """
    return _make_request(JPL_HORIZONS_BASE_URL, command, obj_data, make_ephem, Ephemeris.OBSERVER, observer_data)

@mcp.tool()
async def vectors_request(
    command: str,
    obj_data: bool,
    make_ephem: bool,
    vectors_data: Vectors
) -> dict[str, Any] | None:
    """
    Description here
    """
    return _make_request(JPL_HORIZONS_BASE_URL, command, obj_data, make_ephem, Ephemeris.VECTORS, vectors_data)

@mcp.tool()
async def elements_request(
    command: str,
    obj_data: bool,
    make_ephem: bool,
    elements_data: Elements
) -> dict[str, Any] | None:
    """
    Description here
    """
    return _make_request(JPL_HORIZONS_BASE_URL, command, obj_data, make_ephem, Ephemeris.ELEMENTS, elements_data)

@mcp.tool()
async def spk_request(
    command: str,
    obj_data: bool,
    make_ephem: bool,
    spk_data: Spk
) -> dict[str, Any] | None:
    """
    Description here
    """
    return _make_request(JPL_HORIZONS_BASE_URL, command, obj_data, make_ephem, Ephemeris.SPK, spk_data)

@mcp.tool()
async def approach_request(
    command: str,
    obj_data: bool,
    make_ephem: bool,
    approach_data: Approach
) -> dict[str, Any] | None:
    """
    Description here
    """
    return _make_request(JPL_HORIZONS_BASE_URL, command, obj_data, make_ephem, Ephemeris.APPROACH, approach_data)

### LOOKUP API TO GET THE ID FOR DIFFERENT CELESTIAL BODIES, SPACECRAFT, ETC.

JPL_HORIZONS_LOOKUP_BASE_URL = " https://ssd.jpl.nasa.gov/api/horizons_lookup.api"

class CelestialObjectGroup(StrEnum):
    AST = auto()
    COM = auto()
    PLN = auto()
    SAT = auto()
    SCT = auto()
    MB = auto()
    SB = auto()

async def _make_lookup_request(
    url: str,
    search_string: str,
    group: Optional[CelestialObjectGroup],
) -> dict[str, Any] | None:
    """
    Process a user-specified name, designation, SPK-ID, IAU number, 
    MPC packed designation, or other historical alias, and return 
    in a standardized format its primary synonyms and all aliases 
    recognized by JPL's Horizons system as being linked to publicly 
    available trajectory data.

    Arguments:
        url: base api url
        sstr: search string
        group: what type of object to restrict the search to
    """
    
    # Build the query parameters
    query_params = {
        "format": "json",
        "sstr": search_string,
    }

    if group is not None:
        query_params["group"] = group

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

@mcp.tool()
async def lookup_object_id(
    search_string: str,
    group: Optional[CelestialObjectGroup],
) -> dict[str, Any] | None:
    """
    Process a user-specified name, designation, SPK-ID, IAU number, 
    MPC packed designation, or other historical alias, and return 
    in a standardized format its primary synonyms and all aliases 
    recognized by JPL's Horizons system as being linked to publicly 
    available trajectory data.

    Arguments:
        search_string: Search string containing object name, designation, SPK-ID, IAU number, or MPC packed-format designation
        group: Object group limiter, optionally use none or one: ast to limit search to asteroids only, com for comets only, pln for planets and dynamical points only, sct for spacecraft only, sat for natural satellites only, mb for major body index only, sb small-body index only
    """
    return _make_lookup_request(JPL_HORIZONS_LOOKUP_BASE_URL, search_string, group)