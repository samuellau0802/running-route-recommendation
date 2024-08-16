#### for API calls
import requests

#### for funcs
from geopy import distance
import polyline
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from shapely import Point, LineString


@dataclass
class Route:
    polyline: str
    length: float
    details: dict = field(default_factory=dict)
    closest_point: tuple = field(default_factory=tuple)
    straight_line_distance: float = -1
    google_route_distance: float = -1


@dataclass
class RouteFinder:
    strava_client_id: str
    strava_client_secret: str
    strava_refresh_token: str
    google_api_key: str
    init_cor: Tuple[float]
    cur_cor: Tuple[float] = field(init=False)
    ideal_distance: float    # in km
    strava_nearby_segments: Dict = field(default_factory=dict)
    strava_access_token: str = ""
    init_diag_distance: int = 20
    k: int = 3
    segment_candidates: List[Route] = field(default_factory=list)
    downsample_ratio: int = 1
    STRAVA_CRED_API_URL = "https://www.strava.com/oauth/token"
    STRAVA_API_URL = "https://www.strava.com/api/v3/segments/explore"
    GOOGLE_DISTANCE_API_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
    GOOGLE_MAPS_DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"
    closest_strava_segment: Route = field(init=False)
    route_to_closest_segment: Route = field(init=False)
    result_route: Route = field(init=False)

    def __post_init__(self):
        self.cur_cor = self.init_cor

    def update_strava_access_token(self):
      payload = {
          "client_id": self.strava_client_id,
          "client_secret": self.strava_client_secret,
          'refresh_token': self.strava_refresh_token,
          'grant_type': "refresh_token",
          'f': 'json'
      }
      response = requests.post(self.STRAVA_CRED_API_URL, data=payload, verify=False)
      self.strava_access_token = response.json()['access_token']
      return True

    def get_nearby_strava_segments(self):
        """
        Explore segments around the given coordinates within a specified diagonal distance using the Strava API. A helper function for get_top_k_straight_line_closest_segments_by_start_cors.

        Args:
            self.init_cor (tuple[float]): Tuple of latitude and longitude coordinates.
            self.init_diag_distance (int): Initial bound distance in kilometers.

        Returns:
            dict: JSON response containing the segments found within the bounds.

        Raises:
            Exception: If the API request fails or returns a non-200 status code.
        """
        response = -1
        diag_distance = self.init_diag_distance
        cor = self.init_cor

        # Loop until a segment is found
        while response == -1 or response.json() is None:
            # Calculate the bottom left and upper right bounds based on the given coordinates and diagonal distance
            bottom_left_bound = distance.distance(kilometers=diag_distance/2).destination(cor, bearing=225)
            upper_right_bound = distance.distance(kilometers=diag_distance/2).destination(cor, bearing=45)

            params = {
                "activity_type": "running",
                "bounds": f"{bottom_left_bound[0]}, {bottom_left_bound[1]}, {upper_right_bound[0]}, {upper_right_bound[1]}"
            }
            headers = {
                "Authorization": f"Bearer {self.strava_access_token}"
            }

            response = requests.get(self.STRAVA_API_URL, params=params, headers=headers)

            if response.status_code == 200:
                # If the response is successful but no segments are found, double the bound distance and continue searching
                if response.json() is None:
                    diag_distance *= 2
                else:
                    self.strava_nearby_segments = response.json()
                    return response.json()
            else:
                raise Exception(response.json())

    def get_top_k_straight_line_closest_segments_by_start_cors(self):
        """
        Get the top k closest segments to the given coordinates within a specified diagonal distance. This is used to first screen for segments before using the Google Maps Distance Matrix API to find the actual closest segments.
        self.segment_candidates is updated

        Args:
            self.cur_cor (tuple[float]): Tuple of latitude and longitude coordinates.
            self.k (int): Number of segments to return.
            self.init_diag_distance (int, optional): Initial diagonal distance in kilometers. Defaults to 20.

        Returns:
            bool: True if the function runs successfully.
        """
        segments = self.strava_nearby_segments

        closest_segments = sorted(
            [(segment, distance.geodesic(self.cur_cor, segment['start_latlng']).km) for segment in segments["segments"]],
            key=lambda x: x[1]
        )[:self.k]

        self.segment_candidates = [Route(polyline=s[0]['points'], length=s[0]['distance']/1000, details=s[0]) for s in closest_segments]
        return True

    def get_closest_point_on_segment_candidates(self):
        """
        Get the closest point on each segment candidate to the given coordinates using the Google Maps Distance Matrix API.
        the Route object in self.segment_candidates is updated

        Args:
            self.cur_cor (tuple[float]): Tuple of latitude and longitude coordinates.
            self.segment_candidates (list): List of segment candidates.

        Returns:
            bool: True if the function runs successfully.
        """
        for segment in self.segment_candidates:
            closest_point, straight_line_distance = self.get_closest_point_on_path(polyline.decode(segment.polyline))
            segment.closest_point = closest_point.coords[0]
            segment.straight_line_distance = straight_line_distance

        return True

    def get_closest_point_on_path(self, path: list[tuple]) -> tuple:
        """
        Given a point and a path (list of tuples), find the point on the path that is closest to the given point.
        The distance is calculated as the straight line (geodesic) distance.
        ### https://stackoverflow.com/questions/18900642/get-point-on-a-path-or-polyline-which-is-closest-to-a-disconnected-point
        This is used to compute the point on the path that is closest to the given coordinates in order to put in the Google Maps Distance Matrix API.
        Helper function for get_closest_point_on_segment_candidates.

        Parameters:
        self.cur_cor (tuple): The point as a tuple of (x, y).
        path (list[tuple]): The path as a list of tuples, each representing a point on the path.

        Returns:
        tuple: The closest point on the path to the given point, as a tuple of ((x, y), distance in km).
        """
        p = Point(self.cur_cor)
        path = LineString(path)
        coords = list(path.coords)[::self.downsample_ratio]
        close_points = [(RouteFinder.get_closest_point_on_line(Point(current), Point(next), p), p.distance(Point(next))**2) for current, next in zip(coords[:-1], coords[1:])]

        return min(close_points, key=lambda t: t[1])

    @staticmethod
    def get_closest_point_on_line(start: Point, end: Point, p: Point) -> Point:
        """
        Given a line (defined by a start and end point) and a point, find the point on the line that is closest to the given point.
        The distance is calculated as the straight line (geodesic) distance. A helper function for get_closest_point_on_path.

        Parameters:
        start (Point): The start point of the line, as a shapely.geometry.Point object.
        end (Point): The end point of the line, as a shapely.geometry.Point object.
        p (Point): The point, as a shapely.geometry.Point object.

        Returns:
        Point: The closest point on the line to the given point, as a shapely.geometry.Point object.
        """
        line = LineString([start, end])
        length = line.length**2
        if length == 0.0:
            return start
        v = (end.x - start.x, end.y - start.y)
        param = ((p.x - start.x) * v[0] + (p.y - start.y) * v[1]) / length
        return start if param < 0.0 else end if param > 1.0 else Point(start.x + param * v[0], start.y + param * v[1])

    def get_google_route_distance_on_segment_candidates(self):
        """
        Get the distance between the given coordinates and the closest point on each segment candidate using the Google Maps Distance Matrix API.
        The Route object in self.segment_candidates is updated. Also self.closest_strava_segment is updated.

        Args:
            self.cur_cor (tuple[float]): Tuple of latitude and longitude coordinates.
            self.segment_candidates (list): List of segment candidates.

        Returns:
            bool: True if the function runs successfully.
        """
        for segment in self.segment_candidates:
            params = {
                'origins': f'{self.cur_cor[0]},{self.cur_cor[1]}',
                'destinations': f'{segment.closest_point[0]},{segment.closest_point[1]}',
                'key': self.google_api_key,
                'mode': 'walking',
                'fields': 'distance'
            }
            response = requests.get(self.GOOGLE_DISTANCE_API_URL, params=params).json()
            distance = response['rows'][0]['elements'][0]['distance']['value']
            segment.google_route_distance = distance/1000

        self.closest_strava_segment = sorted(self.segment_candidates, key=lambda x: x.google_route_distance)[0]
        return True

    def get_route_to_closest_segment(self):
        """
        Get the route to the closest segment using the Google Maps Directions API.
        The Route object in self.route_to_closest_segment is updated.

        Args:
            self.cur_cor (tuple[float]): Tuple of latitude and longitude coordinates.
            self.closest_strava_segment (Route): The closest segment.

        Returns:
            bool: True if the function runs successfully.
        """

        # Get the top 3 closest straight line Strava segments based on the start coordinates of the segment
        self.get_top_k_straight_line_closest_segments_by_start_cors()
        # Find the closest point on each segment candidate to the initial coordinate based on straight line distance
        self.get_closest_point_on_segment_candidates()
        # Get the distance between the initial coordinates to the closest point on each segment candidate using the Google Maps Distance Matrix API
        self.get_google_route_distance_on_segment_candidates()

        params = {
            'origin': f'{self.cur_cor[0]},{self.cur_cor[1]}',
            'destination': f'{self.closest_strava_segment.closest_point[0]},{self.closest_strava_segment.closest_point[1]}',
            'key': self.google_api_key,
            'mode': 'walking',

        }
        response = requests.get(self.GOOGLE_MAPS_DIRECTIONS_API_URL, params=params).json()
        polyline = response['routes'][0]['overview_polyline']['points']
        distance = response['routes'][0]['legs'][0]['distance']['value'] / 1000
        self.route_to_closest_segment = Route(polyline=polyline, length=distance, details={}, straight_line_distance=0, google_route_distance=0)
        return True

    def trim_and_complete(self):
        """
        We trim the route to one half of the ideal distance. We also add the remaining one

        Args:
            self.closest_strava_segment (Route): The closest segment.
            self.route_to_closest_segment (Route): The route to the closest segment.

        Returns:
            bool: True if the function runs successfully.
        """
        # Trim the route to one half of the ideal distance
        result_polyline, trimmed_distance = self.trim_route(self.result_route.polyline, self.ideal_distance/2)
        result_polyline += result_polyline[::-1]
        result_polyline = polyline.encode(result_polyline)
        self.result_route = Route(polyline=result_polyline, length=trimmed_distance*2)
        return True

    def combine_route(self, route1, route2):
        """
        concatenating 2 routes by adding their list of coordinates together.

        Args:
            route1 (Route)
            route2 (Route)

        Returns:
            Route: the concatenated route
        """
        result_polyline = polyline.decode(route1.polyline) + polyline.decode(route2.polyline)
        return Route(polyline=polyline.encode(result_polyline), length = route1.length+route2.length)

    def trim_route(self, p: str, d: float) -> str:
        """
        Trim the route to the given distance.

        Args:
            p (str): The polyline of the route.
            d (float): The distance to trim the route to.

        Returns:
            list[tuple]: The trimmed polyline.
        """
        points = polyline.decode(p)
        total_distance = 0
        i = 0
        while total_distance < d and i < len(points)-1:
            total_distance += distance.geodesic(points[i], points[i+1]).km
            i += 1
        return points[:i], total_distance


    def display_route(self, route=-1):
        route = self.result_route if route == -1 else route
        m = folium.Map(location=self.init_cor, zoom_start=15)
        folium.CircleMarker(location=self.init_cor,
                            color="#FF0000",
                            radius=1,
                            weight=9).add_to(m)
        folium.PolyLine(locations=polyline.decode(route.polyline),
                            color="#FF0000",
                            radius=1,
                            weight=7).add_to(m)
        return m

    def init_before_next_search(self):
        self.strava_nearby_segments['segments'].remove(self.closest_strava_segment.details)
        self.cur_cor = self.get_result_route_last_cor()
        self.closest_strava_segment = -1
        self.route_to_closest_segment = -1
        self.segment_candidates = -1
        return True

    def get_result_route_last_cor(self):
        return polyline.decode(self.result_route.polyline)[-1]
    
    def run(self):
        self.update_strava_access_token()
        self.get_nearby_strava_segments()
        # Get the route to the closest segment using the Google Maps Directions API
        self.get_route_to_closest_segment()
        # Complete the route by concat the route to the closest segment and the segment and trim it to one half of the ideal length
        self.result_route = self.combine_route(self.route_to_closest_segment, self.closest_strava_segment)
        while self.result_route.length < self.ideal_distance/2:
            self.init_before_next_search()
            self.get_route_to_closest_segment()
            next_route = self.combine_route(self.route_to_closest_segment, self.closest_strava_segment)
            self.result_route = self.combine_route(self.result_route, next_route)
        self.trim_and_complete()
        return True
