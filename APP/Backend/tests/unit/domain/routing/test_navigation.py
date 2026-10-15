"""Enlaces de Google Maps: formato oficial, codificación y límite de puntos intermedios."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from fleetplanner.domain.routing.navigation import (
    MAX_WAYPOINTS,
    directions_url,
    navigation_legs,
)
from routing_builders import point


def query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


class TestDirectionsUrl:
    def test_uses_the_official_directions_format(self) -> None:
        url = directions_url(point(1))
        parts = urlparse(url)
        assert (parts.scheme, parts.netloc, parts.path) == ("https", "www.google.com", "/maps/dir/")
        q = query(url)
        assert q["api"] == ["1"] and q["travelmode"] == ["driving"]
        assert q["destination"] == [f"{point(1).lat:.6f},{point(1).lon:.6f}"]

    def test_without_an_origin_google_maps_uses_the_phone_location(self) -> None:
        assert "origin" not in query(directions_url(point(1)))

    def test_origin_and_waypoints_are_pipe_separated(self) -> None:
        url = directions_url(point(3), [point(1), point(2)], origin=point(0))
        q = query(url)
        assert q["origin"] == [f"{point(0).lat:.6f},{point(0).lon:.6f}"]
        assert q["waypoints"][0].count("|") == 1
        assert "%7C" in url  # la barra viaja codificada

    def test_no_waypoints_parameter_when_there_are_none(self) -> None:
        assert "waypoints" not in query(directions_url(point(1)))

    def test_the_url_has_no_api_key_and_no_spaces(self) -> None:
        url = directions_url(point(3), [point(1)])
        assert "key=" not in url and " " not in url


class TestLegs:
    def test_a_short_route_is_a_single_link(self) -> None:
        legs = navigation_legs([point(i) for i in range(5)])
        assert len(legs) == 1 and (legs[0].first, legs[0].last) == (0, 5)
        assert len(query(legs[0].url)["waypoints"][0].split("|")) == 4

    def test_never_exceeds_the_maximum_of_intermediate_points(self) -> None:
        legs = navigation_legs([point(i) for i in range(25)])
        for leg in legs:
            waypoints = query(leg.url).get("waypoints", [""])[0]
            assert len(waypoints.split("|") if waypoints else []) <= MAX_WAYPOINTS

    def test_a_long_route_is_chained_so_every_stop_is_covered_once(self) -> None:
        legs = navigation_legs([point(i) for i in range(25)])
        assert [(leg.first, leg.last) for leg in legs] == [(0, 10), (10, 20), (20, 25)]

    def test_each_leg_starts_where_the_previous_one_ended(self) -> None:
        legs = navigation_legs([point(i) for i in range(12)], origin=point(50))
        assert query(legs[0].url)["origin"] == [f"{point(50).lat:.6f},{point(50).lon:.6f}"]
        assert query(legs[1].url)["origin"] == [f"{point(9).lat:.6f},{point(9).lon:.6f}"]

    def test_no_stops_means_no_links(self) -> None:
        assert navigation_legs([]) == []

    def test_a_single_stop_has_only_a_destination(self) -> None:
        (leg,) = navigation_legs([point(4)])
        assert "waypoints" not in query(leg.url)

    def test_custom_limit_is_respected(self) -> None:
        legs = navigation_legs([point(i) for i in range(7)], max_waypoints=2)
        assert [(leg.first, leg.last) for leg in legs] == [(0, 3), (3, 6), (6, 7)]

    def test_negative_limit_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="negativo"):
            navigation_legs([point(1)], max_waypoints=-1)
