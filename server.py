import httpx
from fastmcp import FastMCP
from typing import Any, Optional, Tuple, Protocol
from enum import StrEnum, auto
from dataclasses import dataclass
from datetime import datetime
from functools import reduce

"""
@TODO: For some reason, nested calls to make the request are failing. 
    Put request logic within tool function.
    Fixed for:
    x   - Horizons API  
    x       - Observer
    x       - Vectors
    x       - Elements
    ✓       - Spk
    ✓       - Approach
    ✓   - Horizons Lookup API
    ✓   - Fireball API

@TODO: Fix handling of datetime params to enforce ISO 8601
"""


### INTERNAL UTILITIES
    
class BinaryResponse(StrEnum):
    YES = auto()
    NO = auto()

class Stringable(Protocol):
    def __str__(self) -> str:
        ...
    
def format_to_custom_datetime(dt_obj: datetime) -> str:
    # %Y = Year, %b = Abbreviated month name (e.g., Jul), %d = Day
    # %H = Hour (24h), %M = Minute, %S = Second, %f = Microsecond
    base_str = dt_obj.strftime("%Y-%b-%d %H:%M:%S.%f")
    # Slice off the last 3 digits of microseconds to enforce milliseconds (.fff)
    return base_str[:-3]

def format_to_comma_sep_string(stringable_list) -> str:
    return reduce(lambda x, y: x + y, map(lambda x: str(x), stringable_list))

def format_to_single_quote_string(value) -> str:
    return f"'{value}'"

def format_to_yes_no(value: bool) -> str:
    return "'YES'" if value else "'NO'"

def format_bool(val: bool) -> BinaryResponse:
    if val:
        return BinaryResponse.YES
    return BinaryResponse.NO

### HORIZONS API FOR LOCATIONS

JPL_HORIZONS_BASE_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

class Ephemeris(StrEnum):
    OBSERVER = auto()
    VECTORS = auto()
    ELEMENTS = auto()
    SPK = auto()
    APPROACH = auto()

class CenterEnum(StrEnum):
    COORD = auto()
    GEO = auto()

class CoordTypeEnum(StrEnum):
    GEODETIC = auto()
    CYLINDRICAL = auto()

class CaTableTypeEnum(StrEnum):
    STANDARD = auto()
    EXTENDED = auto()

class TimeDigits(StrEnum):
    MINUTES = auto()
    SECONDS = auto()
    FRACSEC = auto()

class ReferenceFrame(StrEnum):
    ICRF = auto()
    B1950 = auto()

class CalendarFormat(StrEnum):
    CAL = auto()
    JD = auto()
    BOTH = auto()

class CalendarType(StrEnum):
    MIXED = auto()
    GREGORIAN = auto()

class AngleFormat(StrEnum):
    HMS = auto()
    DEG = auto()

class RefractionCorrection(StrEnum):
    AIRLESS = auto()
    REFRACTED = auto()

class DistanceUnits(StrEnum):
    AU = auto()
    KM = auto()

class EphemDataBase:
    pass

@dataclass
class Observer(EphemDataBase):
    Center: CenterEnum
    CoordType: CoordTypeEnum
    SiteCoord: Tuple[float, float, float]
    StartTime: datetime
    StopTime: datetime
    #StepSize:
    TimeDigits: TimeDigits
    #TimeZone: str
    #TList
    #TListType
    #Quantities:
    RefSystem: ReferenceFrame
    CalFormat: CalendarFormat
    CalType: CalendarType
    AngFormat: AngleFormat
    Apparent: RefractionCorrection
    RangeUnits: DistanceUnits
    SuppressRangeRate: bool
    ElevCut: int = -90
    SkipDaylt: bool = False
    #SolarElong: str
    Airmass: float = 38.0
    LhaCutoff: float = 0.0
    AngRateCutoff: float = 0.0
    ExtraPrec: bool = False
    CsvFormat: bool = False
    RTSOnly: bool = False

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
        "format": "json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

@mcp.tool
async def observer_request(
    command: str,
    obj_data: bool,
    make_ephem: bool,
    observer_data: Observer
) -> dict[str, Any] | None:
    """
    Outputs sky coordinates like Right Ascension, Declination, Azimuth, and Elevation. 
    It tells you exactly where a telescope must point to see the object, accounting 
    for factors like atmospheric refraction and Earth's rotation.
    """
    return await _make_request(JPL_HORIZONS_BASE_URL, command, obj_data, make_ephem, Ephemeris.OBSERVER, observer_data)

@mcp.tool
async def vectors_request(
    command: str,
    obj_data: bool,
    make_ephem: bool,
    vectors_data: Vectors
) -> dict[str, Any] | None:
    """
    Outputs raw 3D position and velocity metrics (X, Y, Z, Vx, Vy, Vz). 
    It treats the solar system like a massive grid, ignoring how things look from the ground.
    """
    return await _make_request(JPL_HORIZONS_BASE_URL, command, obj_data, make_ephem, Ephemeris.VECTORS, vectors_data)

@mcp.tool
async def elements_request(
    command: str,
    obj_data: Optional[bool] = True,
    make_ephem: Optional[bool] = True,
    center: Optional[CenterEnum] = CenterEnum.GEO,
    coord_type: Optional[CoordTypeEnum] = CoordTypeEnum.GEODETIC,
    site_coord: Optional[tuple[float,float,float]] = (0.0,0.0,0.0),
    start_time: Optional[datetime] = None,
    stop_time: Optional[datetime] = None,
    step_size: Optional[str] = '60 min',
    time_digits: Optional[TimeDigits] = TimeDigits.MINUTES,
) -> dict[str, Any] | None:
    """
    Outputs geometric orbital parameters (eccentricity, inclination). 
    It describes the overall mathematical shape of the path, not an active position or visual viewing angle
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.ELEMENTS.name.upper() + "'"
    }

    # Optional parameters
    if obj_data is not None:
        query_params["OBJ_DATA"] = format_to_yes_no(obj_data)
    if make_ephem is not None:
        query_params["MAKE_EPHEM"] = format_to_yes_no(make_ephem)
    if center is not None:
        query_params["CENTER"] = format_to_single_quote_string(center.name)
    if coord_type is not None:
        query_params["COORD_TYPE"] = format_to_single_quote_string(coord_type.name.upper())
    if site_coord is not None:
        query_params["SITE_COORD"] = format_to_single_quote_string(format_to_comma_sep_string(site_coord))
    if start_time is not None:
        query_params["START_TIME"] = format_to_single_quote_string(format_to_custom_datetime(start_time))
    if stop_time is not None:
        query_params["STOP_TIME"] = format_to_single_quote_string(format_to_custom_datetime(stop_time))
    if step_size is not None:
        query_params["STEP_SIZE"] = format_to_single_quote_string(step_size)
    if time_digits is not None:
        query_params["TIME_DIGITS"] = time_digits.name.upper()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(JPL_HORIZONS_BASE_URL, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

@mcp.tool
async def spk_request(
    command: str,
    obj_data: Optional[bool] = True,
    make_ephem: Optional[bool] = True,
    start_time: Optional[datetime] = None,
    stop_time: Optional[datetime] = None,
) -> dict[str, Any] | None:
    """
    Download a time-continuous binary SPICE Kernel (SPK) file (.bsp) 
    containing high-precision trajectory and orbit data for a specific solar system body.

    Args:
        command: target search, selection, or enter user-input object mode
        obj_data: toggles return of object summary data
        make_ephem: toggles generation of ephemeris, if possible
        start_time: specifies ephemeris start time
        stop_time: specifies ephemeris stop time
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.SPK.name.upper() + "'"
    }

    # Optional parameters
    if obj_data is not None:
        query_params["OBJ_DATA"] = "'YES'" if obj_data else "'NO'"
    if make_ephem is not None:
        query_params["MAKE_EPHEM"] = "'YES'" if make_ephem else "'NO'"
    if start_time is not None:
        query_params["START_TIME"] = f"'{format_to_custom_datetime(start_time)}'"
    if stop_time is not None:
        query_params["STOP_TIME"] = f"'{format_to_custom_datetime(stop_time)}'"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(JPL_HORIZONS_BASE_URL, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

@mcp.tool
async def close_approach_request(
    command: str,
    obj_data: Optional[bool] = True,
    make_ephem: Optional[bool] = True,
    CaTableType: Optional[CaTableTypeEnum] = CaTableTypeEnum.STANDARD,
    Tca3sgLimit: Optional[int] = 14400,
    CalimSb: Optional[float] = 0.05,
    CalimPl: Optional[Tuple[float, float, float, float, float, float, float, float, float, float]] = (0.1, 0.1, 0.1, 0.1, 1.0, 1.0, 1.0, 1.0, 0.1, 0.003),
) -> dict[str, Any] | None:
    """
    Generate a discrete list of closest-encounter events. 
    Instead of showing where an object is every hour or day, 
    it filters the data to show only the specific moments an 
    asteroid or comet flies past a planet or major moon.

    Args:
        command: target search, selection, or enter user-input object mode
        obj_data: toggles return of object summary data
        make_ephem: toggles generation of ephemeris, if possible
        CaTableType: Extended close-approach tables include Julian Day numbers. B-plane information is also output if there is a covariance for the object stored in the system database or specified with user-input elements.
        Tacs3sgLimit: maximum computed 3-sigma uncertainty in time of Earth close-approach
        CalimSb: sets the spherical radius within which the nominal target must pass one of the perturbing asteroids (Ceres, Pallas, Vesta, etc.) to activate close-approach flagging
        CalimPl: sets the spherical radius within which the nominal target must pass one of the planets (or the Moon) to activate close-approach flagging, in the order: Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto, and Moon
    """
    
    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.APPROACH.name.upper() + "'"
    }

    # Optional parameters
    if obj_data is not None:
        query_params["OBJ_DATA"] = "'YES'" if obj_data else "'NO'"
    if make_ephem is not None:
        query_params["MAKE_EPHEM"] = "'YES'" if make_ephem else "'NO'"
    if CaTableType is not None:
        query_params["CA_TABLE_TYPE"] = f"'{CaTableType.name.upper()}'"
    if Tca3sgLimit is not None:
        query_params["TCA3SG_LIMIT"] = f"'{Tca3sgLimit}'"
    if CalimSb is not None:
        query_params["CALIM_SB"] = f"'{CalimSb}'"
    if CalimPl is not None:
        AsStr = ",".join(map(str, CalimPl))
        query_params["CALIM_PL"] = f"'{AsStr}'"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(JPL_HORIZONS_BASE_URL, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

### LOOKUP API TO GET THE ID FOR DIFFERENT CELESTIAL BODIES, SPACECRAFT, ETC.

JPL_HORIZONS_LOOKUP_BASE_URL = "https://ssd.jpl.nasa.gov/api/horizons_lookup.api"

class CelestialObjectGroup(StrEnum):
    AST = auto()
    COM = auto()
    PLN = auto()
    SAT = auto()
    SCT = auto()
    MB = auto()
    SB = auto()

@mcp.tool
async def lookup_object_id(
    search_string: str,
    group: Optional[CelestialObjectGroup] = None,
) -> dict[str, Any] | None:
    """
    Process a user-specified name, designation, SPK-ID, IAU number, 
    MPC packed designation, or other historical alias, and return 
    in a standardized format its primary synonyms and all aliases 
    recognized by JPL's Horizons system as being linked to publicly 
    available trajectory data. Boo

    Args:
        search_string: Search string containing object name, designation, SPK-ID, IAU number, or MPC packed-format designation
        group: Object group limiter, optionally use none or one: ast to limit search to asteroids only, com for comets only, pln for planets and dynamical points only, sct for spacecraft only, sat for natural satellites only, mb for major body index only, sb small-body index only
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
            response = await client.get(JPL_HORIZONS_LOOKUP_BASE_URL, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None


### FIREBALL TO ACCESS METEOR AND BOLIDE EVENTS

JPL_FIREBALL_BASE_URL = "https://ssd-api.jpl.nasa.gov/fireball.api"

class FireballSortComponent(StrEnum):
    DATE = auto()
    ENERGY = auto()
    #IMPACTENERGY = auto()
    VEL = auto()
    ALT = auto()

class SortOrder(StrEnum):
    ASCENDING = auto()
    DESCENDING = auto()

@mcp.tool
async def fireball_event_lookup(
    date_min: Optional[str] = None, # enforce datetime object better here
    date_max: Optional[str] = None, # ...and here
    energy_min: Optional[float] = None,
    energy_max: Optional[float] = None,
    impact_energy_min: Optional[float] = None,
    impact_energy_max: Optional[float] = None,
    altitude_min: Optional[float] = None,
    altitude_max: Optional[float] = None,
    require_location: Optional[bool] = None,
    require_altitude: Optional[bool] = None,
    require_velocity_component: Optional[bool] = None,
    velocity_component: Optional[bool] = None,
    sort_component: Optional[FireballSortComponent] = None,
    sort_order: Optional[SortOrder] = None,
    limit: Optional[int] = None,
) -> dict[str, Any] | None:
    """
    The fireball data API provides a method of requesting specific records 
    from the available data-set. Every successful query will return content 
    representing one or more fireball data records.

    Args:
        date_min: exclude data earlier than this date YYYY-MM-DD or date/time YYYY-MM-DDThh:mm:ss
        date_max: exclude data later than this date YYYY-MM-DD or date/time YYYY-MM-DDThh:mm:ss
        energy_min: exclude data with total-radiated-energy less than this positive value in joules * 10^10 (e.g., 0.3 = 0.3 * 10^10 joules)
        energy_max: exclude data with total-radiated-energy greater than this (see energy_min)
        impact_energy_min: exclude data with estimated impact energy less than this positive value in kilotons (kt) (e.g., 0.08 kt)
        impact_energy_max: exclude data with total-radiated-energy greater than this (see impact_energy_min)
        altitude_min: exclude data from objects with an altitude less than this (e.g., 22 meaning objects smaller than this)
        altitude_max: exclude data from objects with an altitude greater than this (e.g., 17.75 meaning objects larger than this)
        require_location: location (latitude and longitude) required; when set true, exclude data without a location
        require_altitude: altitude required; when set true, exclude data without an altitude
        require_velocity_component: Entry velocity components required; when set true, exclude data without entry velocity components
        velocity_component: include entry velocity components
        sort_component: which field to sort the resulting data on; “date”, “energy”, “impact-e”, “vel”, or “alt” 
        sort_order: sort the data in ascending or descending order
        limit: limit data to the first N results (where N is the specified number and must be an integer value greater than zero)
    """

    # Build the query parameters
    query_params = {}

    if date_min is not None:
        query_params["date-min"] = date_min
    if date_max is not None:
        query_params["date-max"] = date_max
    if energy_min is not None:
        query_params["energy-min"] = energy_min
    if energy_max is not None:
        query_params["energy-max"] = energy_max
    if impact_energy_min is not None:
        query_params["impact-energy-min"] = impact_energy_min
    if impact_energy_max is not None:
        query_params["impact-energy-max"] = impact_energy_max
    if altitude_min is not None:
        query_params["alt-min"] = altitude_min
    if altitude_max is not None:
        query_params["alt-max"] = altitude_max
    if require_location is not None:
        query_params["req-loc"] = str(require_location).lower()
    if require_altitude is not None:
        query_params["req-alt"] = str(require_altitude).lower()
    if require_velocity_component is not None:
        query_params["req-vel-comp"] = str(require_velocity_component).lower()
    if velocity_component is not None:
        query_params["vel-comp"] = str(velocity_component).lower()
    if sort_component is not None:
        query_params["sort"] = str(sort_component)
    if sort_order is not None:
        if sort_order == SortOrder.DESCENDING:
            query_params["sort"] = "-" + query_params["sort"]
    if limit is not None:
        query_params["limit"] = limit

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(JPL_FIREBALL_BASE_URL, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None