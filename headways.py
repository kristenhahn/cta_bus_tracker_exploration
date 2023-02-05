import requests
from dotenv import load_dotenv
import pandas as pd
import geopandas as gpd
from shapely import Point, LineString
import datetime as dt
import numpy as np
from static_gtfs_analysis import *


# %%
# Get API key from the .env file (for actual headway calcs)
load_dotenv()
API_KEY = os.getenv('API_KEY')

# %%

###########
###########
# Scheduled headways from GTFS feed
###########
###########

# %% [markdown]
# # Calculating Scheduled Headways for CTA Buses - work in progress

# %% [markdown]
# ### What This Does
# 
# - uses chi-hack-night ghost-buses team functions to take in GTFS data for CTA buses
# 
# - uses the trip_summary function from the ghost bus team as a starting point to determine which services are active on a specified route during a specified service day
# 
# - calculates the start and end of each service for every stop on the route that day, based on the scheduled arrival times
# 
# - calculates the overall in-service times for a given bus stop, route, and direction of travel (continuous timeframes when one or more service(s) is active)
# 
# - calculates scheduled headways ONLY for the times service is active on that route/stop/direction of travel.
# This fixes an earlier issue where out-of-service times looked like long headways.
# 
# - calculates scheduled headway statitics for a given bus stop / route / direction of travel
# 
# ## To Do Next
# - Generate a summary table for an entire corridor with headway stats for each stop.
# 
# - Go back to the actual headway calcs and use the in-service times to eliminate "headways" that are actually out-of-service times there too
# 
# - investigate EWT calcs
# 
# 

# %%
import requests
from dotenv import load_dotenv
import pandas as pd
import geopandas as gpd
from shapely import Point, LineString
import datetime as dt
import numpy as np
from static_gtfs_analysis import *

# %% [markdown]
# # Get Scheduled Stop Times and Headways
# 


# %%
# Values to use for testing
gtfs_version_id = '20230105'
route_id = '55'
service_date_string = '2023-01-09'
stop_id = '14122'
direction = 'East'


# %%
# Use Laurie's code to get gtfs feed data
gtfs_feed = download_extract_format(gtfs_version_id)    

# %%
def string_to_datetime(date_string:str) -> pendulum.datetime:
        '''Parameters:\n
        date_string is in the format "YYYY-MM-DD" obtained using get_headways().\n
        Data returned:\n
        specified date as a datetime object.'''
        year = int(date_string[:4])
        month = int(date_string[5:7])
        day = int(date_string[8:])
        return pendulum.datetime(year, month, day)


# %%
def get_stop_details(gtfs_feed:GTFSFeed, route_id:str, service_date_string:str) -> pd.DataFrame:
    
    '''Parameters:\n

    gtfs_feed is obtained using the download_extract_format() function from the ghost bus team.\n

    route_id is a route id as a string (for example, '55' for the 55 Garfield bus)\n

    service_date_string is in the format "YYYY-MM-DD", indicating the service date to be analyzed.
    Note that service dates can include spillover into the next calendar day, for bus routes that run
    past midnight.\n

    Data returned:\n

    DataFrame of scheduled stop information for the route and day, including scheduled
    stop times at every bus stop with service IDs and direction of travel.'''

    service_date = string_to_datetime(service_date_string)

    # Get trip summary for service date using chn-ghost-buses make_trip_summary() function
    trip_summary = make_trip_summary(gtfs_feed, service_date, service_date)

    # filter down to the specified route
    trip_summary = trip_summary[trip_summary['route_id'] == route_id]

    # list trip ids for this route
    trip_list = trip_summary['trip_id'].unique().tolist()

    # get stop times data for the trips on this route
    stop_times = gtfs_feed.stop_times

    # filter stop times down to the relevant trips
    stop_times = stop_times.loc[stop_times['trip_id'].isin(trip_list)]

    # Add service id, route, and direction to the stop times data
    stop_times = stop_times.merge(trip_summary[['trip_id', 'route_id', 'service_id', 'direction', 'raw_date']], on='trip_id')

    # filter stop details down to the relevant route
    stop_times = stop_times.loc[stop_times['route_id'] == route_id]

    # Eliminate duplicates - every line shows up twice.
    # TODO:  Investigate why. Is this related to the calendar_cross line in the 
    # make_trip_summary() function? And/or the fact that I'm using the 
    # same date as start and end date as arguments in make_trip_summary?()
    stop_times = stop_times.drop_duplicates()

    # add stop time as a timestamp
    stop_times['stop_time'] = stop_times['raw_date'] + pd.to_timedelta(stop_times['arrival_time'])

    return stop_times


# %%
# Test
stop_details = get_stop_details(gtfs_feed, route_id, service_date_string)
stop_details

# %%
def get_active_service_times(stop_details:pd.DataFrame, stop_id:str, direction:str) -> list:
    
    '''This is a helper function.\n
    
    Parameters:\n

    stop_details is a dataframe with information on bus stop times
    for a given route and service day.  This is generated by the get_stop_details function.\n

    stop_id is a string representing a single bus stop.\n

    direction is a string representing the direction of travel at this stop to be analyzed: 'North',
    'South', 'East', or 'West'.\n

    Data returned:\n

    List of lists:  each sub-list contains two timestamps representing the start and end of
    an in-service timeframe. These are continuous time ranges when ANY buses on any service 
    for this route and direction are running at a given bus stop.  identifying these will 
    allow us skip out-of-service times in the headway calcs, so those won't show up incorrectly
    as long headways.
    '''

    # dataframe to contain service time ranges
    service_ranges = pd.DataFrame()

    # filter stop details to a single stop and direction of travel
    single_stop_details = stop_details.loc[
        stop_details['stop_id'] == stop_id].loc[
            stop_details['direction'] == direction]
    
    # find service IDs that serve the stop
    service_ids = set(single_stop_details['service_id'])

    # find times when each service starts and ends
    for service_id in service_ids:
        df_service = single_stop_details.loc[single_stop_details['service_id'] == service_id]
        times = df_service['stop_time'].tolist()
        start_time = min(times)
        end_time = max(times)

        # make a single-row dataframe containing start and end times of 
        # one service id at this stop
        df = pd.DataFrame(
            [[service_id, start_time, end_time]],
            columns=['service_id', 'start_time', 'end_time'])

        # Add this service id's time range to the dataframe for all service id's time ranges
        service_ranges = pd.concat([service_ranges, df])

        # sort ranges by start time
        service_ranges.sort_values('start_time', inplace=True)

        # list the start time of the next range
        service_ranges['next_start_time'] = np.roll(service_ranges['start_time'].tolist(), shift=-1,)

        # remove next start time from the last line
        service_ranges['next_start_time'].iloc[-1] = None


    # reset the index
    service_ranges.reset_index(inplace=True)

    # generate a list of start and end times when ANY service is active.
    active_service_times = []
    start_time = 0
    end_time = 0

    # iterate through all service id's time ranges
    for idx, row in service_ranges.iterrows():

        # last range:  set the end time for the current in-service
        # range and add in-service range to the list.
        if idx == len(service_ranges) - 1:
            end_time = row['end_time']
            active_service_times.append((start_time, end_time))

        else:

            #  if there was no service before this range began:
            #  start a new in-service time range with a new start time
            if start_time == 0:
                start_time = row['start_time']


            # if there is a service gap after this range: 
            # this service's end time is the end of the overall in-service time.
            # End the in-service range and add it to the list.
            if row['next_start_time'] > row['end_time']:
                end_time = row['end_time']
                active_service_times.append([start_time, end_time])
                start_time = 0


    return active_service_times


# %%
%%capture --no-display

# Test
get_active_service_times(stop_details, stop_id, direction)

# %%

# Get headways
def get_scheduled_headways(stop_details:pd.DataFrame , stop_id:str, direction:str):

    '''
    Parameters:\n

    stop_details is a dataframe with information on bus stop times
    for a given route and service day.  This is generated by the get_stop_details function.\n

    stop_id is a string representing a single bus stop.\n

    direction is a string representing the direction of travel at this stop to be analyzed: 'North',
    'South', 'East', or 'West'.\n

    Data returned:\n
    '''
    
    # dataframe to contain the output
    df_headways = pd.DataFrame()

    # get the start and end of all timeframes when one or more service is actively 
    # running for the specified stop and direction of travel
    active_service_times = get_active_service_times(stop_details, stop_id, direction)


    # stop details filtered to one stop_id and direction
    df = stop_details.loc[
        stop_details['stop_id'] == stop_id].loc[
            stop_details['direction'] == direction]

    # sort by arrival time
    df = df.sort_values('arrival_time')

    # add previous stop times to each row
    df['previous_stop_time'] = np.roll(df['stop_time'], shift=1)

    # Calculate headways
    df['headway'] = df['stop_time'] - df['previous_stop_time']

    # Remove the first headway and previous stop time for the first
    # bus in each active service period (no previous arrival time to compare with)
    active_service_starts = [start for (start, end) in active_service_times]

    start_filter = df['stop_time'].isin(active_service_starts)

    df.loc[start_filter, 'headway'] = None
    df.loc[start_filter, 'previous_stop_time'] = None

    return df


# %%
    
%%capture --no-display

# Test
headways = get_scheduled_headways(stop_details, stop_id, direction).head(50)

headways

# %%

def get_headway_stats(headways:pd.DataFrame, headway_column_name:LineString) -> dict:
    '''Parameters:\n
    headways is a dataframe obtained using get_headways() or get_scheduled_headways().\n
    headway_column_name is the name of the column containing headways:  'est_headway' if these
    are based on actual bus times using get_headways() or 'scheduled_headway' if these are based
    on GTFS schedules using get_Scheduled_headways()\n
 
    Data returned:\n
    Statisics on the headways are returned as a dictionary.'''
    est_headways = headways[headway_column_name]
    stats = {
        'mean':est_headways.mean(),
        'max':est_headways.max(),
        'min':est_headways.min(),
        '25th_percentile':est_headways.quantile(0.25), # 25th percentile
        'median':est_headways.median(), # 50th percentile
        '75th_percentile':est_headways.quantile(0.75)
    }
    return stats

get_headway_stats(headways, 'headway')


# %%
###########
###########
# Scheduled headways from GTFS feed
###########
###########


# %% [markdown]
# # Calculating Actual Headways for CTA Buses - work in progress

# %% [markdown]
# NOTE: Headways for late night routes are not accurate yet - See the To Do Next section below.
# 
# ### What This Does
# 
# - Calculates actual headways for each CTA bus stop on a given route, direction, service date, and start/end time. Actual headways are based on CTA Bus Tracker GPS data. 
# 
# - Generates summary stats for an entire route (min, max, mean, median, 25th percentile, and 75th percentile headways).
# 
# - Calculate Average Wait Times (AWT) - thanks to Sean MacMullan.
# 
# 
# ## In progress
# 
# - Calculate scheduled headways at each stop, making sure they make sense given different patterns that
# run at different times of day for each route
# 
# 
# ## To Do Next
# 
# - See scheduled_headways.ipynb for functions to ID all periods when buses are in service for a particular route, stop, service, day, and direction of travel.  Use these timeframes (perhaps with a 10 minute or so buffer on either end) to determine start/end times for calculating the actual headways.  This will eliminate the problem of out-of-service times showing up as long headways.
# 
# - Also use the in-service schedule data to determine start/end times of a service day for each stop
# 
# - Add summary stats to the stops geodataframe so they show up in the visualizations when you hover over a stop
# 
# - Investigate EWT calcs Sean found: https://www.trapezegroup.com.au/resources/infographic-how-to-calculate-excess-waiting-time/ 
# 
# - Put all of the actual and scheduled headway code into a .py file
# 
# ## Notes
# 
# One bus route can be made up of several patterns.  Headways are calculated for all buses running the same direction on a given route at a particular stop, regardless which pattern the bus is on.   
# 
# Vehicle data comes from the Chi Hack Night Ghost Buses breakout team: https://ghostbuses.com/about
# This provides location information in 5 minute intervals for every CTA bus.  It includes
# data on which route (rt) and pattern (pid) the bus was running, along with the vehicle's distance along the pattern (pdist) and a timestamp.  
# 
# Pattern data comes from the CTA's API directly. This tells us which stops are found along
# a given pattern and the distance along the pattern where each stop is located.
# 
# ## Strategy for Actual Headways
# 
# Combining the datasets above, the general strategy is:
# 
# 1. Turn vehicle data into intervals:  Time and distance are recorded at the start and end of each 5-minute interval.
# 
# 2. For a given stop and pattern, find all intervals where a vehicle on that pattern reached or pased the stop.
# 
# 3. Estimate the time each bus acutally reached the stop through interpolation.  The interval gives time and distance location along a given pattern before and after the bus arrived at the stop.  The CTA's pattern data tells us where the bus stop falls along the pattern.  Stop times are estimated assuming the vehicle travels a constant spaeed througout the interval.
# 
# 4. Combine all stop times for buses running the same direction at a particular stop.
# 
# 5. Calculate headways between buses based on stop times.
# 
# 6. Calculate summary statistics on headways.
# 



# %% [markdown]
# # Get Actual Stop Times and Headways

# %% [markdown]
# ### Functions

# %%
def get_chn_vehicles(date_string:str, start_timedelta_string:str='02:30', end_timedelta_string:str='26:30') -> pd.DataFrame:
    """Parameters:\n

    date_string in 'YYYY-MM-DD'format\n

    start_timedelta_string in 'hh:mm' format.  (optional. Default is '02:30')\n
    end_timedelta_string in 'hh:mm' format. (optional. Default is '26:30)' \n

    Data returned:\n

    Vehicle data scraped by the chn ghost bus team for all CTA buses running between the specified
    start and end times on the specified date.  Where an end time over 24 hours is specified, the data returned
    will extend into the following calendar date. The maximum valid 
    value for start_timedelta_string or end_timedelta_string is '23:59'\n
    
    Timedelta values start at midnight on day 1.  Example: If start_timedelta_string is '03:45' 
    and end_timedelta_sring is '25:07', then data returned is from 3:45 am on the requested date 
    through 1:07 am the following day. \n
    
    Data is returned in a pandas dataframe. Columns include vehicle id (vid), timestamp (tmstmp), 
    pattern id (pid), and distance along the pattern (pdist) for each vehicle at 5-minute intervals 
    throughout the requested time range on the requested calendar day.
    
    """

    day1 = pd.to_datetime(date_string, infer_datetime_format=True)
    day2 = day1 + pd.Timedelta(days=1)
    day2_string = day2.strftime('%Y-%m-%d')

    start_timedelta_string_expanded = start_timedelta_string + ':00'
    end_timedelta_string_expanded = end_timedelta_string + ':00'

    def get_vehicles_single_day(single_day_datestring):
        chn_data_source_single_day = f'https://chn-ghost-buses-public.s3.us-east-2.amazonaws.com/bus_full_day_data_v2/{single_day_datestring}.csv'
        vehicles_single_day = pd.read_csv(
        chn_data_source_single_day, dtype={
            'vid':'int',
            'tmstmp':'str',
            'lat':'float',
            'lon':'float',
            'hdg':'int',
            'pid':'int',
            'rt':'str',
            'pdist':'int',
            'des':'str',
            'dly':'bool',
            'tatripid':'str',
            'origatripno':'int',
            'tablockid':'str',
            'zone':'str',
            'scrape_file':'str',
            'data_hour':'int',
            'data_date':'str'
            }
        )

        vehicles_single_day['tmstmp'] = pd.to_datetime(vehicles_single_day['tmstmp'],infer_datetime_format=True)
    
        return vehicles_single_day

    df_day1_vehicles = get_vehicles_single_day(date_string)
    df_day2_vehicles = get_vehicles_single_day(day2_string)
    
    df_both_days_vehicles = pd.concat([df_day1_vehicles, df_day2_vehicles])

    # Filter for vehicles running between 2:50 am on day 1 and 2:50 am on day 2.
    # Note:  First tried 2:30, but caught one bus on the test day / route that had their
    # out of service time based on actual stop times from 3:42 am to 4:37 am.  
    # Then changed the window to 3:50am and found another bus stop with a bus
    # at 4:11 and another at 5:50.
    # another 

    # TODO
    # Possible to quickly check every bus route and see if the longest headway is actually
    # an out of service time around 3am?

    service_day_start = day1+pd.Timedelta(start_timedelta_string_expanded)
    service_day_end = day1+pd.Timedelta(end_timedelta_string_expanded)

    df_vehicles = df_both_days_vehicles.loc[
        (service_day_start < df_both_days_vehicles['tmstmp'])
        & (df_both_days_vehicles['tmstmp'] <= service_day_end)]
 
    return df_vehicles


# %%
def get_patterns(vehicles:pd.DataFrame, rt:str) -> pd.DataFrame:
    '''This is a helper function.\n
    Parameters:\n
    vehicles is a dataframe obtained using get_chn_vehicles().\n
    rt is a route id as a string (for example, '55' for the 55 Garfield bus)\n
    Data returned:\n
    patterns data from the CTA's bus tracker API is returned in a dataframe. 
    It includes all pattern ids (pid) found in the in the vehicles data for the specified
    route. Columns include pattern id (pid) and points (pt).\n
    The pt data for each pattern is its own dataframe with information on every point
    along the pattern. It includes columns for sequence (seq), latitude (lat),
    longitude (lon), type of points (typ) where S indicates a bus stop,
    stop ID (stpid) for stop points, and distance along the pattern (pdist).
     '''
    

    df_output = pd.DataFrame()

    # filter vehicles to the specified route
    rt_vehicles = vehicles.loc[vehicles['rt'] == rt]

    # list pid values included in the route
    pid_list = list(rt_vehicles['pid'].unique())

    # convert pids to strings
    pid_list = [str(i) for i in pid_list]

    # split pid_list into chunks of 10 (limit of the API):
    start = 0
    end = len(pid_list)
    step = 10
    for i in range(start, end, step):
        pid_list_chunk = pid_list[i:i+step]
        pid_string = ','.join(pid_list_chunk)

        # get data from CTA's feed
        api_url = f'http://www.ctabustracker.com/bustime/api/v2/getpatterns?key={API_KEY}&pid={pid_string}&format=json'
        response = requests.get(api_url)
        patterns = response.json()

        # convert json to dataframe
        df_patterns = pd.DataFrame(patterns['bustime-response']['ptr'])

        # add to the output dataframe
        df_output = pd.concat([df_output, df_patterns])


    # convert pt column values to dataframes for each pattern containing that pattern's points
    df_output['pt'] = df_output['pt'].apply(lambda x: pd.DataFrame(x))
    
    return df_output


# %%

def get_pattern_linestrings(patterns:pd.DataFrame) -> gpd.GeoDataFrame:
    '''This is for future use and visualization - not neccessary to generate
    headway information.\n
    Paremeters:\n
    patterns is a dataframe obtained using get_patterns().\n
    Data returned:\n
    Pattern data is returned as a geodataframe wiht linestring geometry
    representing the path buses travel.'''

    df_patterns = patterns.copy()

    # Turn points into linestrings
    geometry_linestrings = []
    for p in df_patterns['pt']:
        p.sort_values('seq', inplace=True)
        linestring_points = list(zip(p['lon'],p['lat']))

        # generate linestring using all points
        linestring = LineString(linestring_points)
        geometry_linestrings.append(linestring)

    # Create a geodataframe for the patterns using the linestring geometry
    gdf_patterns = gpd.GeoDataFrame(df_patterns, geometry=geometry_linestrings).set_crs(epsg=4326)

    # Drop the original pt column
    gdf_patterns.drop(['pt'], axis=1, inplace=True)

    return gdf_patterns


# %%
def get_pattern_stops(patterns) -> gpd.GeoDataFrame:
        '''This is a helper function.\n
        Parameters:\n
        patterns is a dataframe obtained using get_patterns().\n
        Data returned:\n
        Bus stop data is returned as a geodataframe 
        with point geomtry, one point per bus stop on each pattern
        associated with a route.\n
        Note that stops serving multiple patterns will be listed multiple 
        times, once for each pattern with the seq and pdist values 
        specific to that pattern.'''

        # get patterns for the route
        df_patterns = patterns.copy()

        # set up a geodataframe to contain stops
        gdf_route_stops = gpd.GeoDataFrame()

        # consider the pid column (pattern ID) and the pt column (dataframe contaning
        # points along the pattern)
        for pid, pt in zip(df_patterns['pid'],df_patterns['pt']):
                # sort points sequentially
                pt.sort_values('seq', inplace=True)
                # add the pattern id to each point's data
                pt['pid']=pid
                # add the pattern direction to each point's data
                rtdir = df_patterns['rtdir'].loc[df_patterns['pid'] == pid].tolist()[0]
                pt['rtdir'] = rtdir
                # filter to only show stop points
                stops = pt[pt['typ']=='S']
                # zip lat/lon data to get coordinate pairs
                coords = list(zip(stops['lon'],stops['lat']))
                # turn coordinates into point geometry
                geometry = [Point(c) for c in coords]
                # generate a geodataframe for the stops in this pattern
                gdf_pattern_stops = gpd.GeoDataFrame(stops,geometry=geometry).set_crs(epsg=4326)
                # add this pattern's stops to the dataframe containing all stops on the route
                gdf_route_stops = pd.concat([gdf_route_stops, gdf_pattern_stops])

        return gdf_route_stops


# %%
def get_vehicle_intervals(vehicles:pd.DataFrame, rt:str) -> pd.DataFrame:

    '''This is a helper function.\n
    Parameters:\n
    vehicles is a dataframe obtained using get_chn_vehicles().\n
    Data returned:\n
    Intervals are returned as a dataframe, with each row representing
    an interval between two points in time and space for one vehicle. 
    Columns are added to the vehicles data for each interval's 
    start time, end time, start pdist, and end pdist.'''

    df_vehicles = vehicles.copy()

    # filter to the specified route
    df_vehicles = df_vehicles.loc[df_vehicles['rt'] == rt]

    # Set up dataframe to contain final fomratted data
    df_output = pd.DataFrame()

    # End time for each interval as a timestamp
    # df_vehicles['end_time'] = pd.to_datetime(df_vehicles['tmstmp'],infer_datetime_format=True)
    df_vehicles['end_time'] = df_vehicles['tmstmp']
    vid_list = df_vehicles['vid'].unique().tolist()

    # End location for each interval
    df_vehicles['end_pdist'] = df_vehicles['pdist']

    for vid in vid_list:

        # pare data down to a single vehicle
        df_vehicle = df_vehicles.loc[df_vehicles['vid'] == vid]

        # handle each pattern separately
        pid_list = df_vehicle['pid'].unique().tolist()
        for p in pid_list:
            df_vehicle_pattern = df_vehicle.loc[df_vehicle['pid']==p].copy()
            # sort by time (it should be sorted already, but just in case)
            df_vehicle_pattern.sort_values(by=['end_time'], inplace=True)

            # Create a start time based on the previous tinmestamp
            end_times = df_vehicle_pattern['end_time'].tolist()
            start_times = np.roll(end_times,shift=1)
            df_vehicle_pattern['start_time'] = start_times

            # Create a start pattern distance based on the previous pdist
            end_distances = df_vehicle_pattern['end_pdist'].tolist()
            start_distances = np.roll(end_distances,shift=1)
            df_vehicle_pattern['start_pdist'] = start_distances

            # Remove the first interval since we don't have real start
            # time or location data for it
            df_vehicle_pattern = df_vehicle_pattern.iloc[1:]

            # add data to the full output dataframe
            df_output = pd.concat([df_output, df_vehicle_pattern])

    return df_output



# %%
def interpolate_stop_time(
    stop_pdist:int, 
    start_time:pd.Timestamp, 
    end_time:pd.Timestamp, 
    start_pdist:int, 
    end_pdist:int
    ) -> pd.Timestamp:

    '''This is a helper function.\n
    Parameters:\n
    stop_pdist is an integer distance along a pattern to a given bus stop.\n
    start_time and end_time are timestamps for the beginning and end of an interval.\n
    start_pdist and end_pdist are integer distances along a pattern at the beginning and
    end of an interval.\n
    Data returned:\n
    timestamp for the estimated time a vehicle reached a stop, assuming it
    traveled a constant speed from start to end of teh interval
    '''

    # How far into the interval distance is the bus stop?
    # stop distance from beginning of interval / full interval distance
    dist_ratio = (stop_pdist-start_pdist)/(end_pdist-start_pdist)

    # estimated bus stop time, assuming it traveled at a steady
    # speed throughout the interval
    est_stop_time = start_time + (end_time - start_time)*dist_ratio

    # round estimated stop time to the nearest minute
    est_stop_time = est_stop_time.round(freq='T')

    return est_stop_time

# %%
def get_stoptimes(rt:str, vehicles:pd.DataFrame) -> pd.DataFrame:

    '''This is a helper function.\n
    Parameters:\n
    vehicles is a dataframe obtained using get_chn_vehicles().\n
    rt is a route id as a string (for example, '55' for the 55 Garfield bus)\n
    Data returned:\n
    Columns are added to the vehicles dataframe indicating the start and end time
    and the start and end distances along a pattern for each interval where a bus
    passed a stop (start_time, end_time, start_pdist, end_pdist). The estimated time 
    each bus actually arrived at the stop (est_stop_time) is also added.\n
    The dataframe returned covers all buses at all stops on the specified route'''
 
    # set up a dataframe to contain the output data
    df_output = pd.DataFrame()

    # turn vehicle data into intervals between vehicles
    vehicle_intervals = get_vehicle_intervals(vehicles, rt)

    # get pattern data from the CTA
    df_patterns = get_patterns(vehicles, rt)

    # get all stops on this route, including all patterns
    gdf_stops = get_pattern_stops(df_patterns)

    # Consider each combination of stop and pattern
    for stpid, pid, rtdir in list(zip(gdf_stops['stpid'],gdf_stops['pid'], gdf_stops['rtdir'])):

        # get a single stop on a single pattern
        gdf_this_stop_pattern = gdf_stops.loc[(gdf_stops['stpid'] == stpid) & (gdf_stops['pid'] == pid)]
        if len(gdf_this_stop_pattern) == 0:
            continue
            
        # Find the bus stop's distance along the pattern
        pdist_this_stop = gdf_this_stop_pattern['pdist'].tolist()[0]

        # find the intervals that are on this pattern
        df_this_pattern_intervals = vehicle_intervals.loc[vehicle_intervals['pid'] == pid]
        if len(df_this_pattern_intervals) == 0:
            continue

        # Filter for intervals that start ahead of the stop location and end at or beyond the stop
        def filter_intervals(stop_dist:int, start_pdist:int, end_pdist:int):
            return (start_pdist < stop_dist) & (end_pdist >= stop_dist)
    
        # Create filter for the intervals we're working on
        interval_filter = df_this_pattern_intervals.apply(
            lambda x: filter_intervals(pdist_this_stop, x['start_pdist'], x['end_pdist']), axis=1
            )
        
        # apply the filter
        df_this_pattern_stop_intervals = df_this_pattern_intervals.loc[interval_filter]
        if len(df_this_pattern_stop_intervals) == 0:
            continue

        # Add stpid, pdist, and rtdir to the data
        df_this_pattern_stop_intervals['stpid'] = stpid
        df_this_pattern_stop_intervals['stop_pdist'] = int(pdist_this_stop)
        df_this_pattern_stop_intervals['rtdir'] = rtdir


        # Estimate time each bus passed the stop (interpolated based on data at start and
        # end of the interval)
        df_this_pattern_stop_intervals['est_stop_time'] = df_this_pattern_stop_intervals.apply(
            lambda x: interpolate_stop_time(
                pdist_this_stop, 
                x['start_time'], 
                x['end_time'], 
                x['start_pdist'], 
                x['end_pdist']), axis=1
            )

        # Add the intervals with stop times to the full output dataframe
        df_output = pd.concat([df_output, df_this_pattern_stop_intervals])

    return df_output


# %%

def get_actual_headways(rt:str, vehicles:pd.DataFrame) -> pd.DataFrame:

        '''Parameters:\n
        vehicles is a dataframe obtained using get_chn_vehicles().\n
        rt is a route id as a string (for example, '55' for the 55 Garfield bus)\n
        Data returned:\n
        Columns are added to the vehicles dataframe indicating the start and end time
        and the start and end distances along a pattern for each interval where a bus
        passed a stop (start_time, end_time, start_pdist, end_pdist), the estimated time 
        each bus actually arrived at the stop (est_stop_time), and headway between each 
        bus (est_headway).  Direction of travel (rtdir) and stop id (stpid)
        are also included.\n
        The dataframe returned covers all buses at all stops on the specified route'''

        df_output = pd.DataFrame()

        # Times buses stopped at each stop on the route
        df_stoptimes = get_stoptimes(rt, vehicles).copy()

        # consider all buses stopping at a given stop moving int he same direction
        for stpid, rtdir in set(zip(df_stoptimes['stpid'], df_stoptimes['rtdir'])):

                # filter data
                df_stop_direction = df_stoptimes.loc[(df_stoptimes['stpid'] == stpid) & (df_stoptimes['rtdir'] == rtdir)]

                # Sort chronologically
                df_stop_direction.sort_values(by='est_stop_time',ascending=True, inplace=True)

                # list stop times in chronological order
                stop_times = df_stop_direction['est_stop_time'].tolist()

                # calculate previous stop time for each line
                prev_stop_times = np.roll(stop_times,1)
                df_stop_direction['previous_stop_time'] = prev_stop_times

                # calculate headway
                df_stop_direction['est_headway'] = (
                df_stop_direction['est_stop_time'] - df_stop_direction['previous_stop_time']
                )
                df_stop_direction['est_headway'] = df_stop_direction['est_headway']

                # drop previous stop time column, no longer needed
                df_stop_direction = df_stop_direction.drop('previous_stop_time', axis=1)

                # Remove headway from the first bus in the dataset since we don't have the 
                # previous bus to compare with
                df_stop_direction['est_headway'].iloc[0] = None
                
                df_output = pd.concat([df_output, df_stop_direction])

        return df_output



# %%
def get_average_wait_time(headways:pd.DataFrame) -> pd.DataFrame:
    '''Parameters:\n
    headways is a dataframe obtained using get_actual_headways().\n
    Data returned:\n
    Average wait time (AWT) value by stop ID.'''

    # AWT = SUM(D^2)/2T, where D = the duration between arrivals and T = the timeframe duration.
    # When D=T, this simplifies to AWT = D/T
    stops = pd.DataFrame()
    stops['stpid'] = headways['stpid'].unique()
    
    AWTs = []
    mean = []
    for stop in stops['stpid']:
        stop_visits = headways[headways['stpid'] == stop]
        
        start = stop_visits['start_time'].min()
        end = stop_visits['end_time'].max()
        timeframe_duration = pd.Timedelta(end-start).seconds/60.0

        headway_minutes = stop_visits['est_headway'].dt.total_seconds()/60
        AWT = ((headway_minutes)**2).sum()/(2*timeframe_duration)
        AWTs.append(AWT)

        mean.append(headway_minutes.mean())

    stops['AWT'] = AWTs
    stops['mean_headway'] = mean
    return stops


# %% [markdown]
# ## Try it out: Get Actual Stop Times and Headways

# %%
vehicles = get_chn_vehicles('2023-01-11')

# %%
vehicles

# %%
%%capture --no-display 
# turn off warnings

# Check out the 90 Ha-rlem bus
headways = get_actual_headways('90',vehicles)


# %%
headways.sort_values('est_headway', ascending=False)

# %%
headway_stats = get_headway_stats(headways, 'est_headway')
headway_stats

# %%
AWTs = get_average_wait_time(headways)
AWTs

# %%
# Visualize routes and stops for the 55 bus (no headway info included in visualization yet)
patterns = get_patterns(vehicles, '55')
route = get_pattern_linestrings(patterns)
stops = get_pattern_stops(patterns)

m = route.explore(color='blue', tiles='CartoDB_positron')
stops.explore(m=m, color='red')


# %%



