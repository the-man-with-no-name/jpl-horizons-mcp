import httpx
import urllib.parse
import sys
import re
from fastmcp import FastMCP
from typing import Any, Annotated
from pydantic import Field
from enum import Enum, StrEnum, auto
from datetime import datetime
from functools import reduce
from geopy.geocoders import Nominatim
from geopy.adapters import AioHTTPAdapter

"""
@TODO: Implement tools for:
    ✓   - Horizons API
    ✓       - Astronomical Data
    ✓       - Observer
    ✓       - Vectors
    ✓           - time list
    ✓          - time range
    ✓       - Elements
    ✓       - Spk
    ✓       - Approach
    ✓   - Horizons Lookup API
    ✓   - Fireball API

@TODO: Add result parsing, LLMs have a hard time parsing the raw text result,
        ephemeris is located between $$SOE and $$EOE tags and can request
        CSV_FORMAT=YES for easier parsing
@TODO: Add coordinate lookup for entering locations as plain text
@TODO: Add elevation lookup for entering locations as plain text
"""

### JPL HORIZONS API INFORMATION

JPL_FIREBALL_BASE_URL = "https://ssd-api.jpl.nasa.gov/fireball.api"
JPL_HORIZONS_LOOKUP_BASE_URL = "https://ssd.jpl.nasa.gov/api/horizons_lookup.api"
JPL_HORIZONS_BASE_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
JPL_HORIZONS_API_SUPPORT_VERSION = "1.2"
JPL_FIREBALL_API_SUPPORT_VERSION = "1.2"
JPL_LOOKUP_API_SUPPORT_VERSION = "1.1"

### OPEN TOPO DATA API INFORMATION

OPEN_TOPO_BASE_URL = "https://api.opentopodata.org/v1"
MAPZEN_DATA = "/mapzen"

### Exceptions

class ApiVersionError(Exception):
    """Exception raised when response version does not match support version"""
    pass

### INTERNAL UTILITIES

# FORMATTING

def format_escape_char_url(value: str) -> str:
    return urllib.parse.quote(value, safe=":")

def format_out_units(value) -> str:
    match value:
        case OutUnits.KMS:
            return "KM-S"
        case OutUnits.AUD:
            return "AU-D"
        case OutUnits.KMD:
            return "KM-D"
        case _:
            return "KM-S"

def format_vec_corr(value: VecCorr) -> str:
    match value:
        case VecCorr.NONE:
            return "NONE"
        case VecCorr.LT:
            return "LT"
        case VecCorr.LTS:
            return "LT+S"
        case _:
            return "NONE"
    
def format_to_custom_datetime(dt_obj: datetime) -> str:
    # %Y = Year, %b = Abbreviated month name (e.g., Jul), %d = Day
    # %H = Hour (24h), %M = Minute, %S = Second, %f = Microsecond
    base_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    # Slice off the last 3 digits of microseconds to enforce milliseconds (.fff)
    return base_str

def format_to_custom_datetime_no_ms(dt_obj: datetime) -> str:
    # %Y = Year, %m = Month, %d = Day
    # %H = Hour (24h), %M = Minute, %S = Second
    base_str = dt_obj.strftime("%Y-%m-%dT%H:%M:%S")
    # Slice off the last 3 digits of microseconds to enforce milliseconds (.fff)
    return base_str

def format_to_comma_sep_string(stringable_list) -> str:
    return reduce(lambda x, y: x + "," + y, map(lambda x: str(x), stringable_list))

def format_to_space_sep_string(stringable_list) -> str:
    return reduce(lambda x, y: x + " " + y, map(lambda x: str(x), stringable_list))

def format_to_single_quote_string(value) -> str:
    return f"'{value}'"

def format_to_yes_no(value: bool) -> str:
    return "'YES'" if value else "'NO'"

def format_to_upper(value: StrEnum) -> str:
    return value.name.upper()

# VERIFICATION

def verify_api_version(response_json: Any, support_version: str) -> None:
    response_version = response_json["signature"]["version"]
    if response_version != support_version:
        raise ApiVersionError(
            f"API response version {response_version} does not" 
            "match support version {JPL_HORIZONS_API_SUPPORT_VERSION}"
        )

def verify_response(response: httpx.Response, support_version: str) -> None:
    response.raise_for_status()
    print("DEBUG: Tool response payload structure:", file=sys.stderr)
    print(response.json(), file=sys.stderr)
    verify_api_version(response.json(), support_version)

# PARSING

def parse_ephemeris(data: str) -> list[str]:
    return re.split(r'\$SOE|\$EOE', data)

### HORIZONS API FOR LOCATIONS

class Ephemeris(StrEnum):
    OBSERVER = auto()
    VECTORS = auto()
    ELEMENTS = auto()
    SPK = auto()
    APPROACH = auto()

class VecTable(Enum):
    POSITION = 1
    STATE = 2
    STATE_LIGHT_RANGE_RATE = 3
    POSITION_LIGHT_RANGE_RATE = 4
    VELOCITY = 5
    LIGHT_RANGE_RATE = 6

class OutUnits(StrEnum):
    KMS = auto()
    AUD = auto()
    KMD = auto()

class VecCorr(StrEnum):
    NONE = auto()
    LT = auto()
    LTS = auto()

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

class TimeStep(StrEnum):
    m = auto()
    h = auto()
    d = auto()
    mo = auto()
    yr = auto()

class TimeListType(StrEnum):
    JD = auto()
    MJD = auto()
    CAL = auto()

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

### MCP Definition

mcp = FastMCP("jpl-horizons-mcp-server")

### Elevation 

@mcp.tool
async def get_elevation_at_coordinates(
    latitude: Annotated[
        float,
        Field(
            description="Latitude of location to obtain " \
            "elevation."
        )
    ],
    longitude: Annotated[
        float,
        Field(
            description="Longitude of location to obtain" \
            "elevation."
        )
    ],
) -> float | None:
    """
    Get the elevation at a coordinate location on earth.
    Coordinate is latitude and longitude.
    """

    query_params = {
        "locations": f"{latitude,longitude}"
    }

    async with httpx.AsyncClient() as client:
        try:
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(
                OPEN_TOPO_BASE_URL + MAPZEN_DATA, 
                params=query_params
            )
            print("DEBUG: Tool response payload structure:", file=sys.stderr)
            print(response.json(), file=sys.stderr)
            result = response.json()
            if "results" in result:
                for location in result["results"]:
                    if "elevation" in location:
                        return location["elevation"]
            return None
        except Exception:
            return None

### Geolocator

@mcp.tool
async def get_coordinates(
    location: Annotated[
        str,
        Field(
            description="Location to obtain the longitude" \
            "and latitude coordinates."
        )
    ]
) -> dict[str, float] | None:
    """
    Get the longitude and latitude coordinates of the 
    provided plain text address or location.
    """
    async with Nominatim(
        user_agent="jpl-horizons-mcp-geolocator",
        adapter_factory=AioHTTPAdapter
    ) as geolocator:
        try:
            coordinates = await geolocator.geocode(location) #type: ignore
            if coordinates is not None:
                return {
                    "latitude": coordinates.latitude,
                    "longitude": coordinates.longitude,
                }
            else:
                raise Exception()
        except Exception:
            return None

### ASTRONOMICAL DATA

@mcp.tool
async def get_astronomical_object_data(
    command: Annotated[
        str, 
        Field(
            description="Identifier of the target body to observe. "
            "Use lookup_object_id first to determine the ID number."
        )
    ],
) -> dict[str, Any] | None:
    """
    Retrieve astronomical object data for the specified target body.
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.OBSERVER.name.upper() + "'",
        "CSV_FORMAT": format_to_yes_no(True),
        "MAKE_EPHEM": format_to_yes_no(False),
        "OBJ_DATA": format_to_yes_no(True),
    }

    async with httpx.AsyncClient() as client:
        try:
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(
                JPL_HORIZONS_BASE_URL, 
                params=query_params
            )
            verify_response(
                response, 
                JPL_HORIZONS_API_SUPPORT_VERSION
            )
            print("DEBUG: Tool response payload structure:", file=sys.stderr)
            print(response.json(), file=sys.stderr)
            return response.json()
        except Exception:
            return None

### ELEMENTS EPHEMERIS

@mcp.tool
async def elements_time_range(
    command: Annotated[
        str, 
        Field(
            description="Identifier of the target body to observe. "
            "Use lookup_object_id first to determine the ID number."
        )
    ],
    coord_type: Annotated[
        CoordTypeEnum | None, 
        Field(
            default=CoordTypeEnum.GEODETIC, 
            description="Select type of user coordinates."
        )
    ],
    site_coord: Annotated[
        list[float], 
        Field(
            default=[0.0,0.0,0.0], 
            description="List of 3 numbers representing the coordinates "
            "of the observer as [longitude, latitude, elevation]"
        )
    ],
    start_time: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="Specify ephemeris start time, "
            "format as '%Y-%b-%d %H:%M:%S.%f'"
        )
    ],
    stop_time: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="Specify ephemeris stop time, "
            "format as '%Y-%b-%d %H:%M:%S.%f'"
        )
    ],
    step_size_amt: Annotated[
        int | None, 
        Field(
            default=None, 
            description="Magnitude of ephemeris time steps."
        )
    ],
    step_size_unit: Annotated[
        TimeStep | None, 
        Field(
            default=None, 
            description="Units of ephemeris time steps."
        )
    ],
) -> dict[str, Any] | None:
    """
    Retrieve geometric orbital parameters (eccentricity, inclination) 
    for the specified command. Geometric orbital parameters describe 
    the overall mathematical shape of the path, not an active position 
    or visual viewing angle.
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.ELEMENTS.name.upper() + "'",
        "CSV_FORMAT": format_to_yes_no(True),
        "OBJ_DATA": format_to_yes_no(False),
        "CENTER": format_to_single_quote_string("coord"),
        "MAKE_EPHEM": format_to_yes_no(True),
    }

    # Optional parameters
    if coord_type is not None:
        query_params["COORD_TYPE"] = format_to_single_quote_string(
            coord_type.name.upper()
        )
    if site_coord is not None:
        query_params["SITE_COORD"] = format_to_single_quote_string(
            format_to_comma_sep_string(
                site_coord
            )
        )
    if start_time is not None:
        query_params["START_TIME"] = format_to_single_quote_string(
            format_to_custom_datetime_no_ms(
                start_time
            )
        )
    if stop_time is not None:
        query_params["STOP_TIME"] = format_to_single_quote_string(
            format_to_custom_datetime_no_ms(
                stop_time
            )
        )
    if step_size_amt is not None and step_size_unit is not None:
        query_params["STEP_SIZE"] = format_to_single_quote_string(
            f"{step_size_amt} {step_size_unit.name}"
        )

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                JPL_HORIZONS_BASE_URL, 
                params=query_params
            )
            verify_response(
                response, 
                JPL_HORIZONS_API_SUPPORT_VERSION
            )
            return response.json()
        except Exception:
            return None

### VECTORS EPHEMERIS

@mcp.tool
async def vectors_time_list(
    command: Annotated[
        str, 
        Field(
            description="Identifier of the target body to observe. " \
            "Use lookup_object_id first to determine the ID number."
        )
    ],
    coord_type: Annotated[
        CoordTypeEnum | None, 
        Field(
            default=CoordTypeEnum.GEODETIC, 
            description="selects type of user coordinates"
        )
    ],
    site_coord: Annotated[
        list[float], 
        Field(
            default=[0.0,0.0,0.0], 
            description="list of 3 numbers representing the coordinates " \
            "of observer in [longitude, latitude, elevation]"
        )
    ],
    time_list: Annotated[
        list[datetime] | None, 
        Field(
            default=None, 
            description="list up to 10,000 discrete output times as " \
            "calendar dates, format as '%Y-%b-%d %H:%M:%S.%f'"
        )
    ],
) -> dict[str, Any] | None:
    """
    Retrieve raw 3D position and velocity metrics (X, Y, Z, Vx, Vy, Vz)
    for the specified command. This treats the solar system like a 
    massive grid, ignoring how things look from the ground.
    Use this command when searching for a specific time or list of times.
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.VECTORS.name.upper() + "'",
        "CSV_FORMAT": format_to_yes_no(True),
        "OBJ_DATA": format_to_yes_no(False),
        "CENTER": format_to_single_quote_string("coord"),
        "MAKE_EPHEM": format_to_yes_no(True),
    }

    # Optional parameters
    if coord_type is not None:
        query_params["COORD_TYPE"] = format_to_single_quote_string(
            coord_type.name.upper()
        )
    if site_coord is not None:
        query_params["SITE_COORD"] = format_to_single_quote_string(
            format_to_comma_sep_string(
                site_coord
            )
        )
    if time_list is not None:
        query_params["TLIST"] = format_to_space_sep_string(
            map(
                format_to_single_quote_string, 
                map(
                    format_to_custom_datetime, time_list
                )
            )
        )

    async with httpx.AsyncClient() as client:
        try:
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(
                JPL_HORIZONS_BASE_URL, 
                params=query_params
            )
            verify_response(response, JPL_HORIZONS_API_SUPPORT_VERSION)
            return response.json()
        except Exception:
            return None
        
@mcp.tool
async def vectors_time_range(
    command: Annotated[
        str, 
        Field(
            description="Identifier of the target body to observe. " \
            "Use lookup_object_id first to determine the ID number."
        )
    ],
    coord_type: Annotated[
        CoordTypeEnum | None, 
        Field(
            default=CoordTypeEnum.GEODETIC, 
            description="selects type of user coordinates"
        )
    ],
    site_coord: Annotated[
        list[float], 
        Field(
            default=[0.0,0.0,0.0], 
            description="list of 3 numbers representing the coordinates " \
            "of observer in [longitude, latitude, elevation]"
        )
    ],
    start_time: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="specifies ephemeris start time, " \
            "format as '%Y-%b-%d %H:%M:%S.%f'"
        )
    ],
    stop_time: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="specifies ephemeris stop time, " \
            "format as '%Y-%b-%d %H:%M:%S.%f'"
        )
    ],
    step_size_amt: Annotated[
        int | None, 
        Field(
            default=None, 
            description="magnitude of ephemeris time step"
        )
    ],
    step_size_unit: Annotated[
        TimeStep | None, 
        Field(
            default=None, 
            description="units of ephemeris time step"
        )
    ],
) -> dict[str, Any] | None:
    """
    Retrieve raw 3D position and velocity metrics (X, Y, Z, Vx, Vy, Vz)
    for the specified command. This treats the solar system like a massive grid, 
    ignoring how things look from the ground. Use this command when searching
    for a range of times at regular intervals.
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.VECTORS.name.upper() + "'",
        "CSV_FORMAT": format_to_yes_no(True),
        "OBJ_DATA": format_to_yes_no(False),
        "CENTER": format_to_single_quote_string("coord"),
        "MAKE_EPHEM": format_to_yes_no(True),
    }

    # Optional parameters
    if coord_type is not None:
        query_params["COORD_TYPE"] = format_to_single_quote_string(
            coord_type.name.upper()
        )
    if site_coord is not None:
        query_params["SITE_COORD"] = format_to_single_quote_string(
            format_to_comma_sep_string(
                site_coord
            )
        )
    if start_time is not None:
        query_params["START_TIME"] = format_to_single_quote_string(
            format_to_custom_datetime_no_ms(
                start_time
            )
        )
    if stop_time is not None:
        query_params["STOP_TIME"] = format_to_single_quote_string(
            format_to_custom_datetime_no_ms(
                stop_time
            )
        )
    if step_size_amt is not None and step_size_unit is not None:
        query_params["STEP_SIZE"] = format_to_single_quote_string(
            f"{step_size_amt} {step_size_unit.name}"
        )

    async with httpx.AsyncClient() as client:
        try:
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(
                JPL_HORIZONS_BASE_URL, 
                params=query_params
            )
            verify_response(response, JPL_HORIZONS_API_SUPPORT_VERSION)
            return response.json()
        except Exception:
            return None

### OBSERVER EPHEMERIS

@mcp.tool
async def observer_request(
    command: Annotated[
        str, 
        Field(
            description="Identifier of the target body to observe. " \
            "Use lookup_object_id first to determine the ID number."
        )
    ],
    coord_type: Annotated[
        CoordTypeEnum | None, 
        Field(
            default=CoordTypeEnum.GEODETIC, 
            description="selects type of user coordinates"
        )
    ],
    site_coord: Annotated[
        list[float], 
        Field(
            default=[0.0,0.0,0.0], 
            description="list of 3 numbers representing the coordinates " \
            "of observer in [longitude, latitude, elevation]"
        )
    ],
    start_time: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="specifies ephemeris start time, " \
            "format as '%Y-%b-%d %H:%M:%S.%f'"
        )
    ],
    stop_time: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="specifies ephemeris stop time, " \
            "format as '%Y-%b-%d %H:%M:%S.%f'"
        )
    ],
    step_size_amt: Annotated[
        int | None, 
        Field(
            default=None, 
            description="magnitude of ephemeris time step"
        )
    ],
    step_size_unit: Annotated[
        TimeStep | None, 
        Field(
            default=None, 
            description="units of ephemeris time step"
        )
    ],
) -> dict[str, Any] | None:
    """
    Retrieve sky coordinates like Right Ascension, Declination, 
    Azimuth, and Elevation. It tells you exactly where a telescope 
    must point to see the object, accounting for factors like 
    atmospheric refraction and Earth's rotation.
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.OBSERVER.name.upper() + "'",
        "CSV_FORMAT": format_to_yes_no(True),
        "OBJ_DATA": format_to_yes_no(False),
        "CENTER": format_to_single_quote_string("coord"),
        "MAKE_EPHEM": format_to_yes_no(True),
    }

    # Optional parameters
    if coord_type is not None:
        query_params["COORD_TYPE"] = format_to_single_quote_string(
            coord_type.name.upper()
        )
    if site_coord is not None:
        query_params["SITE_COORD"] = format_to_single_quote_string(
            format_to_comma_sep_string(
                site_coord
            )
        )
    if start_time is not None:
        query_params["START_TIME"] = format_to_single_quote_string(
            format_to_custom_datetime_no_ms(
                start_time
            )
        )
    if stop_time is not None:
        query_params["STOP_TIME"] = format_to_single_quote_string(
            format_to_custom_datetime_no_ms(
                stop_time
            )
        )
    if step_size_amt is not None and step_size_unit is not None:
        query_params["STEP_SIZE"] = format_to_single_quote_string(
            f"{step_size_amt} {step_size_unit.name}"
        )

    async with httpx.AsyncClient() as client:
        try:
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(
                JPL_HORIZONS_BASE_URL, 
                params=query_params
            )
            verify_response(response, JPL_HORIZONS_API_SUPPORT_VERSION)
            return response.json()
        except Exception:
            return None

### SPK BINARY FILE

@mcp.tool
async def spk_request(
    command: Annotated[
        str, 
        Field(
            description="Identifier of the target body to observe. " \
            "Use lookup_object_id first to determine the ID number."
        )
    ],
    start_time: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="specifies ephemeris start time, " \
            "format as '%Y-%b-%d %H:%M:%S.%f'"
        )
    ],
    stop_time: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="specifies ephemeris stop time, " \
            "format as '%Y-%b-%d %H:%M:%S.%f'"
        )
    ],
) -> dict[str, Any] | None:
    """
    Download a time-continuous binary SPICE Kernel (SPK) file (.bsp) 
    containing high-precision trajectory and orbit data for a 
    specific solar system body.
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.SPK.name.upper() + "'",
        "OBJ_DATA": format_to_yes_no(True),
        "MAKE_EPHEM": format_to_yes_no(True),
    }

    # Optional parameters
    if start_time is not None:
        query_params["START_TIME"] = format_to_single_quote_string(
            format_to_custom_datetime(
                start_time
            )
        )
    if stop_time is not None:
        query_params["STOP_TIME"] = format_to_single_quote_string(
            format_to_custom_datetime(
                stop_time
            )
        )

    async with httpx.AsyncClient() as client:
        try:
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(
                JPL_HORIZONS_BASE_URL, 
                params=query_params
            )
            verify_response(response, JPL_HORIZONS_API_SUPPORT_VERSION)
            return response.json()
        except Exception:
            return None

### CLOSE APPROACH

@mcp.tool
async def close_approach_request(
    command: Annotated[
        str, 
        Field(
            description="target search, selection, "
            "or enter user-input object mode"
        )
    ],
    CaTableType: Annotated[
        CaTableTypeEnum | None, 
        Field(
            default=CaTableTypeEnum.STANDARD, 
            description="Extended close-approach tables include " \
            "Julian Day numbers. B-plane information is also output "
            "if there is a covariance for the object stored in the " \
            "system database or specified with user-input elements."
        )
    ],
    Tca3sgLimit: Annotated[
        int | None, 
        Field(
            default=14400, 
            description="maximum computed 3-sigma uncertainty in " \
            "time of Earth close-approach"
        )
    ],
    CalimSb: Annotated[
        float | None, 
        Field(
            default=0.05, 
            description="sets the spherical radius within which " \
            "the nominal target must pass one of the perturbing " \
            "asteroids (Ceres, Pallas, Vesta, etc.) to activate " \
            "close-approach flagging"
        )
    ],
    CalimPl: Annotated[
        list[float] | None, 
        Field(
            default=[0.1, 0.1, 0.1, 0.1, 1.0, 1.0, 1.0, 1.0, 0.1, 0.003], 
            description="List of 10 float numbers." \
            "Sets the spherical radius within which the " \
            "nominal target must pass one of the planets (or the Moon) " \
            "to activate close-approach flagging, in the order: " \
            "Mercury, Venus, Earth, Mars, Jupiter, Saturn, Uranus, " \
            "Neptune, Pluto, and Moon"
        )
    ],
) -> dict[str, Any] | None:
    """
    Generate a discrete list of closest-encounter events. 
    Instead of showing where an object is every hour or day, 
    it filters the data to show only the specific moments an 
    asteroid or comet flies past a planet or major moon.
    """
    
    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.APPROACH.name.upper() + "'",
        "MAKE_EPHEM": format_to_yes_no(True),
        "OBJ_DATA": format_to_yes_no(False),
    }

    # Optional parameters
    if CaTableType is not None:
        query_params["CA_TABLE_TYPE"] = format_to_single_quote_string(
            CaTableType.name.upper()
        )
    if Tca3sgLimit is not None:
        query_params["TCA3SG_LIMIT"] = format_to_single_quote_string(
            Tca3sgLimit
        )
    if CalimSb is not None:
        query_params["CALIM_SB"] = format_to_single_quote_string(
            CalimSb
        )
    if CalimPl is not None:
        AsStr = ",".join(map(str, CalimPl))
        query_params["CALIM_PL"] = format_to_single_quote_string(
            AsStr
        )

    async with httpx.AsyncClient() as client:
        try:
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(
                JPL_HORIZONS_BASE_URL, 
                params=query_params
            )
            verify_response(response, JPL_HORIZONS_API_SUPPORT_VERSION)
            return response.json()
        except Exception:
            return None

### LOOKUP API TO GET THE ID FOR DIFFERENT CELESTIAL BODIES, SPACECRAFT, ETC.

class CelestialObjectGroup(StrEnum):
    AST = auto()
    COM = auto()
    PLN = auto()
    SAT = auto()
    SCT = auto()
    MB = auto()
    SB = auto()

### OBJECT ID LOOKUP

@mcp.tool
async def lookup_object_id(
    search_string: Annotated[
        str, 
        Field(
            description="Search string containing object name, " \
            "designation, SPK-ID, IAU number, or " \
            "MPC packed-format designation"
        )
    ],
    group: Annotated[
        CelestialObjectGroup | None, 
        Field(
            default=None, 
            description="Object group limiter, optionally use " \
            "none or one: ast to limit search to asteroids only, " \
            "com for comets only, pln for planets and dynamical " \
            "points only, sct for spacecraft only, sat for natural " \
            "satellites only, mb for major body index only, " \
            "sb small-body index only"
        )
    ],
) -> dict[str, Any] | None:
    """
    Process a user-specified name, designation, SPK-ID, IAU number, 
    MPC packed designation, or other historical alias, and return 
    in a standardized format its primary synonyms and all aliases 
    recognized by JPL's Horizons system as being linked to publicly 
    available trajectory data.
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
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(
                JPL_HORIZONS_LOOKUP_BASE_URL, 
                params=query_params
            )
            verify_response(response, JPL_LOOKUP_API_SUPPORT_VERSION)
            return response.json()
        except Exception:
            return None


### FIREBALL TO ACCESS METEOR AND BOLIDE EVENTS

class FireballSortComponent(StrEnum):
    DATE = auto()
    ENERGY = auto()
    IMPACT = auto()
    VEL = auto()
    ALT = auto()

class SortOrder(StrEnum):
    ASCENDING = auto()
    DESCENDING = auto()

def format_fireball_sort_component(sort_component: FireballSortComponent) -> str:
    match sort_component:
        case FireballSortComponent.DATE:
            return "date"
        case FireballSortComponent.ENERGY:
            return "energy"
        case FireballSortComponent.IMPACT:
            return "impact-e"
        case FireballSortComponent.VEL:
            return "vel"
        case FireballSortComponent.ALT:
            return "alt"
        case _:
            return "date"

### FIREBALL EVENTS

@mcp.tool
async def fireball_event_lookup(
    date_min: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="Exclude data earlier than this date " \
            "YYYY-MM-DD or date/time YYYY-MM-DDThh:mm:ss"
        )
    ],
    date_max: Annotated[
        datetime | None, 
        Field(
            default=None, 
            description="Exclude data later than this date " \
            "YYYY-MM-DD or date/time YYYY-MM-DDThh:mm:ss"
        )
    ],
    energy_min: Annotated[
        float | None, 
        Field(
            default=None, 
            description="Exclude data with total-radiated-energy " \
            "less than this positive value in joules * 10^10 "
            "(e.g., 0.3 = 0.3 * 10^10 joules)"
        )
    ],
    energy_max: Annotated[
        float | None, 
        Field(
            default=None, 
            description="Exclude data with total-radiated-energy " \
            "more than this positive value in joules * 10^10 "
            "(e.g., 0.3 = 0.3 * 10^10 joules)"
        )
    ],
    impact_energy_min: Annotated[
        float | None, 
        Field(
            default=None, 
            description="exclude data with estimated impact energy " \
            "less than this positive value in kilotons "
            "(kt) (e.g., 0.08 kt)"
        )
    ],
    impact_energy_max: Annotated[
        float | None, 
        Field(
            default=None, 
            description="exclude data with estimated impact energy " \
            "more than this positive value in kilotons (kt) "
            "(e.g., 0.08 kt)"
        )
    ],
    altitude_min: Annotated[
        float | None, 
        Field(
            default=None, 
            description="exclude data from objects with an altitude " \
            "less than this (e.g., 22 meaning objects smaller than this)"
        )
    ],
    altitude_max: Annotated[
        float | None, 
        Field(
            default=None, 
            description="exclude data from objects with an altitude " \
            "greater than this (e.g., 17.75 meaning objects " \
            "smaller than this)"
        )
    ],
    require_location: Annotated[
        bool | None, 
        Field(
            default=None, 
            description="location (latitude and longitude) " \
            "required; when set true, exclude data without " \
            "a location"
        )
    ],
    require_altitude: Annotated[
        bool | None, 
        Field(
            default=None, 
            description="altitude required; when set true, " \
            "exclude data without an altitude"
        )
    ],
    require_velocity_component: Annotated[
        bool | None, 
        Field(
            default=None, 
            description="Entry velocity components required; " \
            "when set true, exclude data without entry " \
            "velocity components"
        )
    ],
    velocity_component: Annotated[
        bool | None, 
        Field(
            default=None, 
            description="include entry velocity components"
        )
    ],
    sort_component: Annotated[
        FireballSortComponent | None, 
        Field(
            default=None, 
            description="which field to sort the resulting " \
            "data on; 'date', 'energy', 'impact-e', 'vel', "
            "or 'alt'"
        )
    ],
    sort_order: Annotated[
        SortOrder | None, 
        Field(
            default=None, 
            description="sort the data in ascending or " \
            "descending order"
        )
    ],
    limit: Annotated[
        int | None, 
        Field(
            default=None, 
            description="limit data to the first N results "
            "(where N is the specified number and must be an " \
            "integer value greater than zero)", 
            ge=1
        )
    ],
) -> dict[str, Any] | None:
    """
    The fireball data API provides a method of requesting specific records 
    from the available data-set. Every successful query will return content 
    representing one or more fireball data records.
    """

    # Build the query parameters
    query_params = {}

    if date_min is not None:
        query_params["date-min"] = format_to_custom_datetime_no_ms(date_min)
    if date_max is not None:
        query_params["date-max"] = format_to_custom_datetime_no_ms(date_max)
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
        query_params["sort"] = format_fireball_sort_component(sort_component)
    if sort_order is not None:
        if sort_order == SortOrder.DESCENDING:
            query_params["sort"] = "-" + query_params["sort"]
    if limit is not None:
        query_params["limit"] = limit

    async with httpx.AsyncClient() as client:
        try:
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(
                JPL_FIREBALL_BASE_URL, 
                params=query_params
            )
            verify_response(response, JPL_FIREBALL_API_SUPPORT_VERSION)
            return response.json()
        except Exception:
            return None