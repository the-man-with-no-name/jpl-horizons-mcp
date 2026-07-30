import httpx
import urllib.parse
import sys
from fastmcp import FastMCP
from typing import Any, Optional, Tuple, Protocol, Annotated, Literal
from pydantic import Field
from enum import Enum, StrEnum, auto
from dataclasses import dataclass
from datetime import datetime
from functools import reduce

"""
@TODO: For some reason, nested calls to make the request are failing. 
    Put request logic within tool function.
    Fixed for:
    x   - Horizons API  
    x       - Observer
    ✓       - Vectors
    ✓       - Elements
    ✓       - Spk
    ✓       - Approach
    ✓   - Horizons Lookup API
    ✓   - Fireball API

@TODO: Fix handling of datetime params to enforce ISO 8601
@TODO: Elements and Observer request may be swapped, check and fix
"""


### INTERNAL UTILITIES
    
class BinaryResponse(StrEnum):
    YES = auto()
    NO = auto()

class Stringable(Protocol):
    def __str__(self) -> str:
        ...

def format_escape_char_url(value) -> str:
    return urllib.parse.quote(value)

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

def format_vec_corr(value) -> str:
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
    base_str = dt_obj.strftime("%Y-%b-%d %H:%M:%S.%f")
    # Slice off the last 3 digits of microseconds to enforce milliseconds (.fff)
    return base_str[:-3]

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

#@mcp.tool
async def elements_request(
    command: str,
    obj_data: bool,
    make_ephem: bool,
    observer_data: Observer
) -> dict[str, Any] | None:
    """
    Determine geometric orbital parameters (eccentricity, inclination) for the specified command. 
    Geometric orbital parameters describe the overall mathematical shape of the path, 
    not an active position or visual viewing angle.
    """
    return await _make_request(JPL_HORIZONS_BASE_URL, command, obj_data, make_ephem, Ephemeris.ELEMENTS, observer_data)

@mcp.tool
async def vectors_time_list(
    command: str,
    obj_data: Optional[bool] = False,
    make_ephem: Optional[bool] = True,
    center: Optional[str] = None,
    coord_type: Optional[CoordTypeEnum] = CoordTypeEnum.GEODETIC,
    site_coord: Optional[tuple[float,float,float]] = (0.0,0.0,0.0),
    # start_time: Optional[datetime] = None,
    # stop_time: Optional[datetime] = None,
    # step_size_amt: Optional[int] = None,
    # step_size_unit: Optional[TimeStep] = None,
    # time_digits: Optional[TimeDigits] = TimeDigits.MINUTES,
    time_list: Optional[list[str]] = None,
    #time_list_type: Optional[TimeListType] = None,
    # ref_system: Optional[ReferenceFrame] = ReferenceFrame.ICRF,
    # out_units: Optional[OutUnits] = OutUnits.KMS,
    # vec_table: Optional[VecTable] = VecTable.STATE_LIGHT_RANGE_RATE,
    # vec_corr: Optional[VecCorr] = VecCorr.NONE,
    # cal_type: Optional[CalendarType] = CalendarType.MIXED,
    # csv_format: Optional[bool] = False,
    # vec_labels: Optional[bool] = False,
    # vec_delta_t: Optional[bool] = False,
) -> dict[str, Any] | None:
    """
    Obtain raw 3D position and velocity metrics (X, Y, Z, Vx, Vy, Vz) for the specified command.
    This treats the solar system like a massive grid, ignoring how things look from the ground.

    Args:
        command: target search, selection, or enter user-input object mode
        obj_data: toggles return of object summary data
        make_ephem: toggles generation of ephemeris, if possible
        center: selects coordinate origin (observing site), format as "site@body"
        coord_type: selects type of user coordinates
        time_list: list up to 10,000 discrete output times as calendar dates, format as "%Y-%b-%d %H:%M:%S.%f"
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.VECTORS.name.upper() + "'"
    }

    # start_time: specifies ephemeris start time
    # stop_time: specifies ephemeris stop time
    # step_size_amt: magnitude of ephemeris time step
    # step_size_unit: units of ephemeris time step
    # time_digits: controls output time precision
    # time_list_type: override default assumptions, specify type of time used in time_list
    # ref_system: specifies reference frame for any geometric and astrometric quantities
    # out_units: selects output units for distance and time; for example, AU-D selects astronomical units (au) and days (d)
    # vec_table: selects vector table format
    # vec_corr: selects level of correction to output vectors; NONE (geometric states), LT (astrometric light-time corrected states) or LT+S (astrometric states corrected for stellar aberration)
    # cal_type: Selects Gregorian-only calendar input/output, or mixed Julian/Gregorian, switching on 1582-Oct-5. Recognized for close-approach tables also.
    # csv_format: toggles output of table in comma-separated value format
    # vec_labels: toggles labeling of each vector component
    # vec_delta_t: toggles output of the time-varying delta-T difference TDB-UT

    # Optional parameters
    if obj_data is not None:
        query_params["OBJ_DATA"] = format_to_yes_no(obj_data)
    if make_ephem is not None:
        query_params["MAKE_EPHEM"] = format_to_yes_no(make_ephem)
    if center is not None:
        query_params["CENTER"] = format_to_single_quote_string(center)
    if coord_type is not None:
        query_params["COORD_TYPE"] = format_to_single_quote_string(coord_type.name.upper())
    if site_coord is not None:
        query_params["SITE_COORD"] = format_to_single_quote_string(format_to_comma_sep_string(site_coord))
    # if start_time is not None:
    #     query_params["START_TIME"] = format_to_single_quote_string(format_to_custom_datetime(start_time))
    # if stop_time is not None:
    #     query_params["STOP_TIME"] = format_to_single_quote_string(format_to_custom_datetime(stop_time))
    # if step_size_amt is not None and step_size_unit is not None:
    #     query_params["STEP_SIZE"] = format_to_single_quote_string(f"{step_size_amt} {step_size_unit.name}")
    # if time_digits is not None:
    #     query_params["TIME_DIGITS"] = time_digits.name.upper()
    if time_list is not None:
        query_params["TLIST"] = format_escape_char_url(format_to_space_sep_string(map(format_to_single_quote_string, time_list)))
    # if time_list_type is not None:
    #     query_params["TLIST_TYPE"] = time_list_type.name.upper()
    # if ref_system is not None:
    #     query_params["REF_SYSTEM"] = ref_system.name.upper()
    # if out_units is not None:
    #     query_params["OUT_UNITS"] = format_out_units(out_units)
    # if vec_table is not None:
    #     query_params["VEC_TABLE"] = f"{vec_table.value}"
    # if vec_corr is not None:
    #     query_params["VEC_CORR"] = format_vec_corr(vec_corr)
    # if cal_type is not None:
    #     query_params["CAL_TYPE"] = cal_type.name.upper()
    # if csv_format is not None:
    #     query_params["CSV_FORMAT"] = format_to_yes_no(csv_format)
    # if vec_labels is not None:
    #     query_params["VEC_LABELS"] = format_to_yes_no(vec_labels)
    # if vec_delta_t is not None:
    #     query_params["VEC_DELTA_T"] = format_to_yes_no(vec_delta_t)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(JPL_HORIZONS_BASE_URL, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None
        
@mcp.tool
async def vectors_time_range(
    command: str,
    obj_data: Optional[bool] = False,
    make_ephem: Optional[bool] = True,
    center: Optional[str] = None,
    coord_type: Optional[CoordTypeEnum] = CoordTypeEnum.GEODETIC,
    site_coord: Optional[tuple[float,float,float]] = (0.0,0.0,0.0),
    start_time: Optional[datetime] = None,
    stop_time: Optional[datetime] = None,
    step_size_amt: Optional[int] = None,
    step_size_unit: Optional[TimeStep] = None,
    # time_digits: Optional[TimeDigits] = TimeDigits.MINUTES,
    # time_list: Optional[list[str]] = None,
    # time_list_type: Optional[TimeListType] = None,
    # ref_system: Optional[ReferenceFrame] = ReferenceFrame.ICRF,
    # out_units: Optional[OutUnits] = OutUnits.KMS,
    # vec_table: Optional[VecTable] = VecTable.STATE_LIGHT_RANGE_RATE,
    # vec_corr: Optional[VecCorr] = VecCorr.NONE,
    # cal_type: Optional[CalendarType] = CalendarType.MIXED,
    # csv_format: Optional[bool] = False,
    # vec_labels: Optional[bool] = False,
    # vec_delta_t: Optional[bool] = False,
) -> dict[str, Any] | None:
    """
    Obtain raw 3D position and velocity metrics (X, Y, Z, Vx, Vy, Vz) for the specified command.
    This treats the solar system like a massive grid, ignoring how things look from the ground.

    Args:
        command: target search, selection, or enter user-input object mode
        obj_data: toggles return of object summary data
        make_ephem: toggles generation of ephemeris, if possible
        center: selects coordinate origin (observing site), format as "site@body"
        coord_type: selects type of user coordinates
        start_time: specifies ephemeris start time, format as "%Y-%b-%d %H:%M:%S.%f"
        stop_time: specifies ephemeris stop time, format as "%Y-%b-%d %H:%M:%S.%f"
        step_size_amt: magnitude of ephemeris time step
        step_size_unit: units of ephemeris time step
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.VECTORS.name.upper() + "'"
    }

    # time_digits: controls output time precision
    # time_list: list up to 10,000 discrete output times, either Julian Day numbers (JD), modified Julian Day numbers (MJD), or calendar dates
    # time_list_type: override default assumptions, specify type of time used in time_list
    # ref_system: specifies reference frame for any geometric and astrometric quantities
    # out_units: selects output units for distance and time; for example, AU-D selects astronomical units (au) and days (d)
    # vec_table: selects vector table format
    # vec_corr: selects level of correction to output vectors; NONE (geometric states), LT (astrometric light-time corrected states) or LT+S (astrometric states corrected for stellar aberration)
    # cal_type: Selects Gregorian-only calendar input/output, or mixed Julian/Gregorian, switching on 1582-Oct-5. Recognized for close-approach tables also.
    # csv_format: toggles output of table in comma-separated value format
    # vec_labels: toggles labeling of each vector component
    # vec_delta_t: toggles output of the time-varying delta-T difference TDB-UT

    # Optional parameters
    if obj_data is not None:
        query_params["OBJ_DATA"] = format_to_yes_no(obj_data)
    if make_ephem is not None:
        query_params["MAKE_EPHEM"] = format_to_yes_no(make_ephem)
    if center is not None:
        query_params["CENTER"] = format_to_single_quote_string(center)
    if coord_type is not None:
        query_params["COORD_TYPE"] = format_to_single_quote_string(coord_type.name.upper())
    if site_coord is not None:
        query_params["SITE_COORD"] = format_to_single_quote_string(format_to_comma_sep_string(site_coord))
    if start_time is not None:
        query_params["START_TIME"] = format_to_single_quote_string(format_to_custom_datetime(start_time))
    if stop_time is not None:
        query_params["STOP_TIME"] = format_to_single_quote_string(format_to_custom_datetime(stop_time))
    if step_size_amt is not None and step_size_unit is not None:
        query_params["STEP_SIZE"] = format_to_single_quote_string(f"{step_size_amt} {step_size_unit.name}")
    # if time_digits is not None:
    #     query_params["TIME_DIGITS"] = time_digits.name.upper()
    # if time_list is not None:
    #     query_params["TLIST"] = format_escape_char_url(format_to_space_sep_string(map(format_to_single_quote_string, time_list)))
    # if time_list_type is not None:
    #     query_params["TLIST_TYPE"] = time_list_type.name.upper()
    # if ref_system is not None:
    #     query_params["REF_SYSTEM"] = ref_system.name.upper()
    # if out_units is not None:
    #     query_params["OUT_UNITS"] = format_out_units(out_units)
    # if vec_table is not None:
    #     query_params["VEC_TABLE"] = f"{vec_table.value}"
    # if vec_corr is not None:
    #     query_params["VEC_CORR"] = format_vec_corr(vec_corr)
    # if cal_type is not None:
    #     query_params["CAL_TYPE"] = cal_type.name.upper()
    # if csv_format is not None:
    #     query_params["CSV_FORMAT"] = format_to_yes_no(csv_format)
    # if vec_labels is not None:
    #     query_params["VEC_LABELS"] = format_to_yes_no(vec_labels)
    # if vec_delta_t is not None:
    #     query_params["VEC_DELTA_T"] = format_to_yes_no(vec_delta_t)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(JPL_HORIZONS_BASE_URL, params=query_params)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

@mcp.tool
async def observer_request(
    command: str,
    obj_data: Optional[bool] = False,
    make_ephem: Optional[bool] = True,
    center: Optional[str] = None,
    coord_type: Optional[CoordTypeEnum] = CoordTypeEnum.GEODETIC,
    site_coord: Optional[tuple[float,float,float]] = (0.0,0.0,0.0),
    start_time: Optional[datetime] = None,
    stop_time: Optional[datetime] = None,
    step_size_amt: Optional[int] = None,
    step_size_unit: Optional[TimeStep] = None,
    # time_digits: Optional[TimeDigits] = TimeDigits.MINUTES,
    # time_zone: Optional[str] = None,
    # time_list: Optional[list[str]] = None,
    # time_list_type: Optional[TimeListType] = None,
    # ref_system: Optional[ReferenceFrame] = ReferenceFrame.ICRF,
    # cal_format: Optional[CalendarFormat] = CalendarFormat.CAL,
    # cal_type: Optional[CalendarType] = CalendarType.MIXED,
    # ang_format: Optional[AngleFormat] = AngleFormat.HMS,
    # apparent: Optional[RefractionCorrection] = RefractionCorrection.AIRLESS,
    # range_units: Optional[DistanceUnits] = DistanceUnits.AU,
    # suppress_range_rate: Optional[bool] = False,
    # elev_cut: Optional[int] = -90,
    # skip_daylt: Optional[bool] = False,
    # solar_elong: Optional[Tuple[int,int]] = (0,180), 
    # airmass: Optional[float] = 38.0,
    # lha_cutoff: Optional[float] = 0.0,
    # ang_rate_cutoff: Optional[float] = 0.0,
    # extra_prec: Optional[bool] = False,
    # csv_format: Optional[bool] = False,
    # rts_only: Optional[bool] = False,
) -> dict[str, Any] | None:
    """
    Outputs sky coordinates like Right Ascension, Declination, Azimuth, and Elevation. 
    It tells you exactly where a telescope must point to see the object, accounting 
    for factors like atmospheric refraction and Earth's rotation.

    Args:
        command: target search, selection, or enter user-input object mode
        obj_data: toggles return of object summary data
        make_ephem: toggles generation of ephemeris, if possible
        center: selects coordinate origin (observing site), format as "site@body"
        coord_type: selects type of user coordinates
        start_time: specifies ephemeris start time, format as "%Y-%b-%d %H:%M:%S.%f"
        stop_time: specifies ephemeris stop time, format as "%Y-%b-%d %H:%M:%S.%f"
        step_size_amt: magnitude of ephemeris time step
        step_size_unit: units of ephemeris time step
    """

    # Build the query parameters
    query_params = {
        "format": "json",
        "COMMAND": "'" + command + "'",
        "EPHEM_TYPE": "'" + Ephemeris.OBSERVER.name.upper() + "'"
    }

    # time_digits: controls output time precision
    # time_zone: specifies local civil time offset relative to UT
    # time_list: list up to 10,000 discrete output times, either Julian Day numbers (JD), modified Julian Day numbers (MJD), or calendar dates
    # time_list_type: override default assumptions, specify type of time used in time_list
    # ref_system: specifies reference frame for any geometric and astrometric quantities
    # cal_format: selects type of date output; CAL for calendar date/time, JD for Julian Day numbers, or BOTH for both CAL and JD
    # cal_type: Selects Gregorian-only calendar input/output, or mixed Julian/Gregorian, switching on 1582-Oct-5. Recognized for close-approach tables also.
    # ang_format: selects RA/DEC output format
    # apparent: toggles refraction correction of apparent coordinates (Earth topocentric only)
    # range_units: sets the units on range quantities output
    # suppress_range_rate: turns off output of delta-dot and rdot (range-rate)
    # elev_cut: skip output when object elevation is less than specified
    # skip_daylt: toggles skipping of print-out when daylight at CENTER
    # solar_elong: sets bounds on output based on solar elongation angle
    # airmass: select airmass cutoff; output is skipped if relative optical airmass is greater than the single decimal value specified. Note than 1.0=zenith, 38.0 ~= local-horizon. If value is set >= 38.0, this turns OFF the filtering effect.
    # lha_cutoff: skip output when local hour angle exceeds a specified value in the domain 0.0 < X < 12.0. To restore output (turn OFF the cut-off behavior), set X to 0.0 or 12.0. For example, a cut-off value of 1.5 will output table data only when the LHA is within +/- 1.5 angular hours of zenith meridian.
    # ang_rate_cutoff: skip output when the total plane-of-sky angular rate exceeds a specified value
    # extra_prec: toggles additional output digits on some angles such as RA/DEC
    # csv_format: toggles output of table in comma-separated value format
    # rts_only: toggles output only at target rise/transit/set

    # Optional parameters
    if obj_data is not None:
        query_params["OBJ_DATA"] = format_to_yes_no(obj_data)
    if make_ephem is not None:
        query_params["MAKE_EPHEM"] = format_to_yes_no(make_ephem)
    if center is not None:
        query_params["CENTER"] = format_to_single_quote_string(center)
    if coord_type is not None:
        query_params["COORD_TYPE"] = format_to_single_quote_string(coord_type.name.upper())
    if site_coord is not None:
        query_params["SITE_COORD"] = format_to_single_quote_string(format_to_comma_sep_string(site_coord))
    if start_time is not None:
        query_params["START_TIME"] = format_to_single_quote_string(format_to_custom_datetime(start_time))
    if stop_time is not None:
        query_params["STOP_TIME"] = format_to_single_quote_string(format_to_custom_datetime(stop_time))
    if step_size_amt is not None and step_size_unit is not None:
        query_params["STEP_SIZE"] = format_to_single_quote_string(f"{step_size_amt} {step_size_unit.name}")
    # if time_digits is not None:
    #     query_params["TIME_DIGITS"] = time_digits.name.upper()
    # if time_zone is not None:
    #     query_params["TIME_ZONE"] = format_to_single_quote_string(time_zone)
    # if time_list is not None:
    #     query_params["TLIST"] = format_escape_char_url(format_to_space_sep_string(map(format_to_single_quote_string, time_list)))
    # if time_list_type is not None:
    #     query_params["TLIST_TYPE"] = time_list_type.name.upper()
    # if ref_system is not None:
    #     query_params["REF_SYSTEM"] = ref_system.name.upper()
    # if cal_format is not None:
    #     query_params["CAL_FORMAT"] = cal_format.name.upper()
    # if cal_type is not None:
    #     query_params["CAL_TYPE"] = cal_type.name.upper()
    # if ang_format is not None:
    #     query_params["ANG_FORMAT"] = ang_format.name.upper()
    # if apparent is not None:
    #     query_params["APPARENT"] = apparent.name.upper()
    # if range_units is not None:
    #     query_params["RANGE_UNITS"] = range_units.name.upper()
    # if suppress_range_rate is not None:
    #     query_params["SUPPRESS_RANGE_RATE"] = format_to_yes_no(suppress_range_rate)
    # if elev_cut is not None:
    #     query_params["ELEV_CUT"] = format_to_single_quote_string(elev_cut)
    # if skip_daylt is not None:
    #     query_params["SKIP_DAYLT"] = format_to_yes_no(skip_daylt)
    # if solar_elong is not None:
    #     query_params["SOLAR_ELONG"] = format_to_single_quote_string(format_to_comma_sep_string(solar_elong))
    # if airmass is not None:
    #     query_params["AIRMASS"] = f"{airmass}"
    # if lha_cutoff is not None:
    #     query_params["LHA_CUTOFF"] = f"{lha_cutoff}"
    # if ang_rate_cutoff is not None:
    #     query_params["ANG_RATE_CUTOFF"] = f"{ang_rate_cutoff}"
    # if extra_prec is not None:
    #     query_params["EXTRA_PREC"] = format_to_yes_no(extra_prec)
    # if csv_format is not None:
    #     query_params["CSV_FORMAT"] = format_to_yes_no(csv_format)
    # if rts_only is not None:
    #     query_params["R_T_S_ONLY"] = format_to_yes_no(rts_only)

    async with httpx.AsyncClient() as client:
        try:
            print("DEBUG: Tool query params:", file=sys.stderr)
            print(query_params, file=sys.stderr)
            response = await client.get(JPL_HORIZONS_BASE_URL, params=query_params)
            response.raise_for_status()
            print("DEBUG: Tool response payload structure:", file=sys.stderr)
            print(response.json(), file=sys.stderr)
            return response.json()
        except Exception:
            return None

@mcp.tool
async def spk_request(
    command: str,
    obj_data: Optional[bool] = False,
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
        start_time: specifies ephemeris start time, format as "%Y-%b-%d %H:%M:%S.%f"
        stop_time: specifies ephemeris stop time, format as "%Y-%b-%d %H:%M:%S.%f"
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
    obj_data: Optional[bool] = False,
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
    search_string: Annotated[str, Field(description="Search string containing object name, designation, SPK-ID, IAU number, or MPC packed-format designation")],
    group: Annotated[CelestialObjectGroup | None, Field(default=None, description="Object group limiter, optionally use none or one: ast to limit search to asteroids only, com for comets only, pln for planets and dynamical points only, sct for spacecraft only, sat for natural satellites only, mb for major body index only, sb small-body index only")],
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
    date_min: Annotated[datetime | None, Field(default=None, description="Exclude data earlier than this date YYYY-MM-DD or date/time YYYY-MM-DDThh:mm:ss")],
    date_max: Annotated[datetime | None, Field(default=None, description="Exclude data later than this date YYYY-MM-DD or date/time YYYY-MM-DDThh:mm:ss")],
    energy_min: Annotated[float | None, Field(default=None, description="Exclude data with total-radiated-energy less than this positive value in joules * 10^10 (e.g., 0.3 = 0.3 * 10^10 joules)")],
    energy_max: Annotated[float | None, Field(default=None, description="Exclude data with total-radiated-energy more than this positive value in joules * 10^10 (e.g., 0.3 = 0.3 * 10^10 joules)")],
    impact_energy_min: Annotated[float | None, Field(default=None, description="exclude data with estimated impact energy less than this positive value in kilotons (kt) (e.g., 0.08 kt)")],
    impact_energy_max: Annotated[float | None, Field(default=None, description="exclude data with estimated impact energy more than this positive value in kilotons (kt) (e.g., 0.08 kt)")],
    altitude_min: Annotated[float | None, Field(default=None, description="exclude data from objects with an altitude less than this (e.g., 22 meaning objects smaller than this)")],
    altitude_max: Annotated[float | None, Field(default=None, description="exclude data from objects with an altitude greater than this (e.g., 17.75 meaning objects smaller than this)")],
    require_location: Annotated[bool | None, Field(default=None, description="location (latitude and longitude) required; when set true, exclude data without a location")],
    require_altitude: Annotated[bool | None, Field(default=None, description="altitude required; when set true, exclude data without an altitude")],
    require_velocity_component: Annotated[bool | None, Field(default=None, description="Entry velocity components required; when set true, exclude data without entry velocity components")],
    velocity_component: Annotated[bool | None, Field(default=None, description="include entry velocity components")],
    sort_component: Annotated[FireballSortComponent | None, Field(default=None, description="which field to sort the resulting data on; 'date', 'energy', 'impact-e', 'vel', or 'alt'")],
    sort_order: Annotated[SortOrder | None, Field(default=None, description="sort the data in ascending or descending order")],
    limit: Annotated[int | None, Field(default=None, description="limit data to the first N results (where N is the specified number and must be an integer value greater than zero)", ge=1)],
) -> dict[str, Any] | None:
    """
    The fireball data API provides a method of requesting specific records 
    from the available data-set. Every successful query will return content 
    representing one or more fireball data records.
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