# Jet Propulsion Laboratory Horizons MCP

[JPL Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html) MCP to access ephemeris data for astronomical objects.

## Overview 

Model Context Protocol (MCP) implementation of some the APIs, including:

* Horizons Lookup API: Process a user-specified name, designation, SPK-ID, IAU number, MPC packed designation, or other historical alias, and return in a standardized format its primary synonyms and all aliases recognized by JPL’s Horizons system as being linked to publicly available trajectory data. This API is intended for telescope schedulers and others who need to correlate one of the many object labels typically possible with Horizons output and other sources.

* Fireball Data API: The fireball data API provides a method of requesting specific records from the available data-set. Every successful query will return content representing one or more fireball data records. See the CNEOS page on fireballs for details on this data-set.

* Horizons API: This API provides access to JPL’s Horizons system by specifying Horizons settings as parameters in the URL. An alternate file-based Horizons API is available if you would prefer to submit a Horizons batch input file via HTTP POST.

## Supporting Tools

Additional tools are included to support those provided to access the JPL APIs, including:

* Geopy: Resolve the latitude and longitude coordinates of a lookup location provided as a plaintext string.

* Open Topo Data: Retrieve the elevation at a specified coordinate.

## Installation

To install, clone this repository with

    git clone https://github.com/the-man-with-no-name/jpl-horizons-mcp.git

## Serve

To run the MCP server, use `uv`. For example, to use `http` transport and access the server on port `3030`, use:

    uv run fastmcp run main.py --transport http --port 3030
