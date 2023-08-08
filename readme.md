Learning about APIs while exploring CTA Bus Tracker data.  Inspired by and based on the work of
https://github.com/chihacknight/chn-ghost-buses.

A CTA Bus Tracker API key is required.  Create one by following the instructions at 
https://www.transitchicago.com/developers/bustracker/

More information on the CTA Bus Tracker API is available here:
https://www.transitchicago.com/assets/1/6/cta_Bus_Tracker_API_Developer_Guide_and_Documentation_20160929.pdf

Create a .env file in your project, and add:
API_KEY='your_key_here'

### CAUTION:  
### Headway data is NOT valid for bus stops near the ends of a route.
  This code relies on 5-minute snapshot data to determine when a bus has passed a given stop.  For a bus stop within 5 minutes travel time of the end of a route, the bus may be captured before the stop but there will be no data point past the stop.  Therefore, these buses are not accurately captured in this data set.

### What headways.py does:  Overview

For a quick hands-on view of what this code does, see jupyter notebook at https://github.com/kristenhahn/cta_bus_tracker_exploration/blob/main/all_headways_all_stops_single_route.ipynb.

- Calculates active service times for a given bus stop and direction of travel. These are continuous time ranges when ANY buses on any service for this route and direction are scheduled to be running at a given bus stop. Identifying these active service times allows us to skip out-of-service periods in the headway calcs so they don't show up incorrectly as long headways.  Active service times are based on gtfs schedule information, and they are specific to each bus stop and direction of travel.

- Calculates all scheduled headways at a bus stop on a specified date within the active service times.  Scheduled headways are based on gtfs bus schedules scraped using code from the chi-hack-night team.

- Calculates actual bus arrival times at each stop.  The chi-hack-night team scraped real-time bus location data at 5-minute intervals.  Actual bus stop times are estimated through interpolation, assuming each bus travels a constant speed from the timestamp and location immediately before it reaches a stop to the timestamp and location immediately after the stop is passed.

- Calculates all actual headways at a bus stop on a given route, direction, and service date based on the actual bus arrival times.  Headways are only captured for buses arriving at the stop within the in-service  times for that stop. 

- Generates summary stats for an entire route (min, max, mean, median, 25th percentile, and 75th percentile headways at all stops)

- Produces a geoPandas geoDataFrame including all bus stops for a given route and day, with summary stats at each stop.  Saves it as a geoJSON file.

- Calculate Average Wait Times (AWT) - thanks to Sean MacMullan.  Not yet included in geoDataFrame and geoJSON files.

- Generates detailed headway information for a given bus stop, route, and date:  Bus arrival times with headways are provided for every bus throughout the day. These can be generated for both scheduled buses from gtfs information and actual buses from realtime bus data.

## Notes on bus routes and patterns

One bus route can be made up of several patterns.  Headways are calculated for all buses running the same direction on a given route at a particular stop, regardless which pattern the bus is on.   

Vehicle data comes from the Chi Hack Night Ghost Buses breakout team: https://ghostbuses.com/about
This provides location information in 5 minute intervals for every CTA bus.  It includes
data on which route (rt) and pattern (pid) the bus was running, along with the vehicle's distance along the pattern (pdist) and a timestamp.  

Pattern data comes from the CTA's API directly. This tells us which stops are found along
a given pattern and the distance along the pattern where each stop is located.

## Detailed approach:  Active Service Times

1. Use chi-hack-night ghost-buses team functions to take in GTFS data for CTA buses

2. Use the trip_summary function from the ghost bus team as a starting point to determine which services are active on a specified route during a specified service day

3. Calculate the start and end of each service for every stop on the route that day, based on the scheduled arrival times

4. Calculate the overall in-service times for a given bus stop, route, and direction of travel (continuous timeframes when one or more service(s) is/are active)

5. Calculate headways ONLY for the times service is active on that route/stop/direction of travel. This fixes an earlier issue where out-of-service times looked like long headways.  

## Detailed approach:  Scheduled Headways

1. Get gtfs-feed data for all stops on a given route and day.  

2. Filter down to the specified bus stop and direction of travel.

2. Calculate scheduled headways between buses based on stop times.  (Stop time of current bus - stop time of previous bus)

3. Calculate summary statistics on scheduled headways for this bus stop and route (total daily buses, mean, 25th Percentile, median, 75th percentile)


## Detailed Approach: Actual Stop Times and Headways

1. See caution above. Headway data is NOT valid for bus stops near the ends of a route.

2. Turn vehicle data into intervals:  Time and distance are recorded at the start and end of each 5-minute interval.

3. For a given stop and pattern, find all intervals where a vehicle on that pattern reached or passed the stop.

4. Calculate the approximate time each bus actually reached the stop through interpolation.  The interval gives time and distance location along a given pattern before and after the bus arrived at the stop.  The CTA's pattern data tells us where the bus stop falls along the pattern.  Stop times are estimated assuming the vehicle travels a constant spaeed througout the interval.

5. Combine all stop times for buses running the same direction at a particular stop into a dataFrame.

6. Calculate actual headways between buses based on stop times.  (Stop time of current bus - stop time of previous bus)

Note: If a bus arrives outside of the active service times expected for a given bus stop, that bus will not be counted in the headway calculations for that stop.  For each active service time range, headways are calculated starting with the second bus arriving in the active service time range (because there has to be a previous bus to set the start of the headway interval).   Headway calculations end with the last bus in the active service time range.

7. Calculate summary statistics on actual headways for this bus stop and route (total daily buses, mean, 25th Percentile, median, 75th percentile)

Note that the total daily bus number may be off by 1-2 even if all buses are running.  Any bus that arrives slightly outside the expected active service times will not be counted.  See to do list below.

## To Do

- Investigate how to address bus stops near the end of a route (see the caution message above)

- Investigate adding 5-10 minutes to the beginning and end of each active service interval, so that slightly early/late buses in the realtime data are accounted for in the actual headway data.

- Investigate why stops are duplicated in the summary data for some routes in the geoDataFrames and geoJSON files.

- Investigate EWT calcs Sean found: https://www.trapezegroup.com.au/resources/infographic-how-to-calculate-excess-waiting-time/ 



