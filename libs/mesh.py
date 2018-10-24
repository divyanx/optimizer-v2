# coding=utf-8
"""
Mesh module
"""

import math
import logging
from operator import attrgetter, itemgetter
from typing import Optional, Tuple, List, Sequence, Generator

from shapely.geometry.polygon import Polygon
from shapely.geometry import Point, LineString, LinearRing
import numpy as np
import matplotlib.pyplot as plt

from libs.utils.custom_types import Vector2d, SpaceCutCb, Coords2d
from libs.utils.geometry import magnitude, ccw_angle, nearest_point
from libs.utils.geometry import (
    unit_vector,
    normalized_vector,
    barycenter,
    move_point,
    same_half_plane,
    opposite_vector
)
from libs.plot import random_color, make_arrow, plot_polygon, plot_edge, plot_save


# MODULE CONSTANTS

# arbitrary value for the length of the line :
# it should be long enough to approximate infinity
LINE_LENGTH = 500000
ANGLE_EPSILON = 1  # value to check if an angle has a specific value
COORD_EPSILON = 1  # coordinates precision for snapping purposes
MIN_ANGLE = 10.0  # min. acceptable angle in grid
COORD_DECIMAL = 2  # number of decimal of the points coordinates


# MODULE FUNCTIONS

def angle_pseudo_equal(angle: float, value: float) -> bool:
    """
    Verify if an angle is very close to a specific value
    :param angle: float
    :param value: float
    :return: boolean
    """
    return value + ANGLE_EPSILON > angle > value - ANGLE_EPSILON


# MODULE CLASSES

class Vertex:
    """
    Vertex class
    """
    def __init__(self, x: float = 0, y: float = 0, edge: 'Edge' = None):
        """
        A simple Vertex class with barycentric capability
        By default sets the vertex to the origin (0, 0)
        :param x: float, x-axis coordinates
        :param y: float, y-axis coordinates
        :param edge: one edge starting from the vertex
        """
        self._x = float(np.around(float(x), decimals=COORD_DECIMAL))
        self._y = float(np.around(float(y), decimals=COORD_DECIMAL))
        self._edge = edge
        # attributes used to store barycenter data
        self._parents = None  # a tuple (vertex 1, vertex 2)
        self._coeff = None  # barycenter coefficient

    def __repr__(self):
        return 'vertex: ({x}, {y}) - {i}'.format(x=self.x, y=self.y, i=id(self))

    @property
    def x(self) -> float:
        """
        property
        :return: the x coordinate
        """
        return self._x

    @x.setter
    def x(self, value: float):
        """
        property
        Sets the x coordinate
        """
        self._x = float(value)

    @property
    def y(self) -> float:
        """
        property
        :return: the y coordinate
        """
        return self._y

    @y.setter
    def y(self, value: float):
        """
        property
        Sets the y coordinate
        """
        self._y = float(value)

    @property
    def edge(self):
        """
        property
        :return: the edge of the vertex
        """
        return self._edge

    @edge.setter
    def edge(self, value: 'Edge'):
        """
        property
        Sets the edge the vertex starts
        """
        self._edge = value

    @property
    def parents(self) -> Tuple:
        """
        property
        :return: the parents vertices of a barycentric vertex as a tuple
        """
        return self._parents

    @parents.setter
    def parents(self, value: Tuple):
        """
        property
        Sets the parents of a barycentric vertex
        """
        self._parents = value

    @property
    def coeff(self) -> float:
        """
        property
        :return: the parents vertices of a barycentric vertex as a tuple
        """
        return self._coeff

    @coeff.setter
    def coeff(self, value):
        """
        property
        Sets the parents of a barycentric vertex
        """
        self._parents = value

    @property
    def coords(self):
        """
        Returns the coordinates of the vertex in the form of a tuple
        :return:
        """
        return self.x, self.y

    @property
    def as_sp(self):
        """
        Returns a shapely Point data structure
        :return: shapely Point
        """
        return Point(self.x, self.y)

    @property
    def previous(self):
        """
        Returns the previous vertex according to edge flow
        :return: vertex
        """
        return self.edge.previous.start

    @property
    def next(self):
        """
        Returns the next vertex according to edge flow
        :return: vertex
        """
        return self.edge.next.start

    @property
    def edges(self) -> Generator['Edge', None, None]:
        """
        Returns all edges starting from the vertex
        :return: generator
        """
        yield self.edge
        edge = self.edge.previous.pair
        while edge is not self.edge:
            yield edge
            edge = edge.previous.pair

    @property
    def mesh(self) -> 'Mesh':
        """
        Returns the mesh containing the vertex
        :return: mesh
        """
        if self.edge.face is None:
            return self.edge.pair.face.mesh

        return self.edge.face.mesh

    def barycenter(self,
                   vertex_1: 'Vertex',
                   vertex_2: 'Vertex',
                   coeff: float) -> 'Vertex':
        """
        Sets the coordinates to the barycenter of the given vertices
        and stores the information
        :param vertex_1:
        :param vertex_2:
        :param coeff: barycentric coefficient (starting from first vertex)
        :return: self
        """
        if coeff == 0:
            return vertex_1

        if coeff == 1:
            return vertex_2

        if coeff > 1 or coeff < 0:
            raise Exception('A barycenter coefficient' +
                            'should have a value between 0 and 1')

        self.parents = vertex_1, vertex_2
        self.coeff = coeff
        self.x, self.y = barycenter(vertex_1.coords, vertex_2.coords, coeff)

        return self

    def clean(self):
        """
        Removes an unneeded vertex.
        It is a vertex that is used only by one edge.
        :return: self or None
        """
        edges = list(self.edges)
        nb_edges = len(edges)
        # check the number of edges starting from the vertex
        if nb_edges > 2:
            logging.info('Cannot clean a vertex used by more than one edge')
            return
        # only a vertex with two edges can be cleaned
        if nb_edges == 2:
            if edges[0].previous.pair is not edges[1]:
                raise ValueError('Vertex is malformed' +
                                 ' and cannot be cleaned:{0}'.format(self))
            if self.edge.previous.next_is_aligned:
                edge = self.edge
                # preserve references
                edge.preserve_references()
                edge.pair.next.preserve_references()
                # remove edges
                edge.previous.next = edge.next
                edge.pair.next = edge.pair.next.next

    def is_equal(self, other: 'Vertex') -> bool:
        """
        Pseudo equality operator in order
        to avoid near misses due to floating point precision
        :param other:
        :return:
        """
        return self.distance_to(other) < COORD_EPSILON

    def nearest_point(self, face: 'Face') -> 'Vertex':
        """
        Returns the nearest point on the perimeter of the given face,
        to the vertex
        :param face:
        :return: vertex
        """
        point = nearest_point(self.as_sp, face.as_sp_linear_ring())
        return Vertex(*point.coords[0])

    def project_point(self, face: 'Face', vector: Vector2d) -> Tuple['Vertex', 'Edge', float]:
        """
        Returns the projected point according to the vector direction
        on the face boundary according to the provided vector.
        Note the vertex has to be inside the face.
        :param face:
        :param vector:
        :return: a tuple containing the new vertex and the associated edge, and the distance from
        the projected vertex
        """
        # check whether the face contains the vertex
        if not face.as_sp.intersects(self.as_sp):
            raise ValueError('Can not project a vertex' +
                             ' that is outside the face: {0} - {1}'.format(self, face))

        # find the intersection
        closest_edge = None
        intersection_point = None
        smallest_distance = None

        # iterate trough every edge of the face but the laser_cut edge
        for edge in face.edges:

            # do not project on edges that starts or end with the vertex
            if self in (edge.start, edge.end):
                continue

            # check if the edge is facing the correct direction
            angle_vector_edge = ccw_angle(vector, edge.normal)
            if angle_vector_edge <= 90.0 or angle_vector_edge >= 270.0:
                continue

            # we use shapely to compute the intersection point
            # create an extended shapely lineString from the edge
            sp_edge = edge.as_sp_extended
            # create a line to the edge at the vertex position
            sp_line = self.sp_line(vector)
            temp_intersection_point = sp_edge.intersection(sp_line)

            # we are only interested in a clean intersection
            # meaning only one Point
            if temp_intersection_point.geom_type != 'Point':
                continue

            new_distance = sp_line.project(temp_intersection_point)

            # only keep the closest point
            if not smallest_distance or new_distance < smallest_distance:
                smallest_distance = new_distance
                closest_edge = edge
                intersection_point = temp_intersection_point

        return (Vertex(*intersection_point.coords[0]),
                closest_edge,
                smallest_distance) if smallest_distance else None

    def distance_to(self, other: 'Vertex') -> float:
        """
        Returns the distance between the vertex and another
        :param other: vertex
        :return: float
        """
        vector = self.x - other.x, self.y - other.y
        return magnitude(vector)

    def snap_to(self, *others: 'Vertex') -> 'Vertex':
        """
        Used to snap a vertex to another one that is closed.
        The function returns the first vertex from the argument list
        that is localized inside the approximation radius
        (given by the pseudo equality is_equal)
        or self if no vertex is close enough
        example : vertex_to_snap = vertex_to_snap.snap_to(v1, v2, v3)
        :param others: one or many vertices
        :return: a vertex
        """
        for other in others:
            # case we try to snap a vertex to itself
            if self is other:
                return self
            if self.is_equal(other):
                # ensure that the reference to the vertex are still valid
                if self.edge is not None:
                    for edge in list(self.edges):
                        edge.start = other
                return other
        return self

    def snap_to_edge(self, *edges: 'Edge') -> Optional['Edge']:
        """
        Snaps a vertex to an edge if the vertex is close enough to the edge
        we split the edge and insert the vertex
        We snap to the first edge close enough
        :param edges: edges to check
        :return: the newly created edge if a snap happened, None otherwise
        """
        for edge in edges:
            dist = edge.as_sp.distance(self.as_sp)
            if dist < COORD_EPSILON:
                return edge.split(self)
        return None

    def sp_line(self,
                vector: Vector2d,
                length: float = LINE_LENGTH) -> LineString:
        """
        Returns a shapely LineString starting
        from the vertex and following the vector
        and of the given length
        :param vector: direction of the lineString
        :param length: float length of the lineString
        :return:
        """
        start_point = self.coords
        end_point = (start_point[0] + vector[0] * length,
                     start_point[1] + vector[1] * length)
        return LineString([start_point, end_point])


class Edge:
    """
    Half Edge class
    """
    def __init__(self,
                 start: Optional[Vertex],
                 next_edge: Optional['Edge'],
                 face: Optional['Face'],
                 pair: Optional['Edge'] = None,
                 space_next: Optional['Edge'] = None,
                 linear=None):
        """
        A half edge data structure implementation.
        By convention our half edge structure is based on a CCW rotation.

        :param start: Vertex starting point for the edge
        :param pair: twin edge of opposite face
        :param face: the face that the edge belongs to,
        can be set to None for external edges
        :param next_edge: the next edge
        """
        self._start = start
        self._next = next_edge
        self._face = face
        # always add a pair Edge, because an edge should always have a pair edge
        self._pair = pair if pair else Edge(None, None, None, self)
        self._space_next = space_next
        self.linear = linear

        # check the size of the edge
        self.check_size()

    def __repr__(self):
        output = 'Edge: '
        # output += 'id:{0}'.format(id(self))
        output += ' [({x1}, {y1}), ({x2},{y2})]'.format(x1=self.start.x,
                                                        y1=self.start.y,
                                                        x2=self.end.x,
                                                        y2=self.end.y)
        # output += ' - f:{0}'.format(id(self.face))
        # output += ' - n:{0}'.format(id(self.next))

        return output

    @property
    def start(self) -> Vertex:
        """
        property
        :return: the starting vertex of the edge
        """
        return self._start

    @start.setter
    def start(self, value: Vertex):
        """
        property
        Sets the starting vertex of the edge
        """
        self._start = value

    @property
    def pair(self) -> 'Edge':
        """
        property
        :return: the pair Edge of the edge
        """
        return self._pair

    @pair.setter
    def pair(self, value: 'Edge'):
        """
        property
        Sets the pair Edge of the edge
        """
        self._pair = value
        # a pair should always be reciprocal
        # note: we cannot use the setter because it will induce an infinite loop
        value._pair = self

    @property
    def next(self) -> 'Edge':
        """
        property
        :return: the next Edge of the edge
        """
        return self._next

    @next.setter
    def next(self, value: 'Edge'):
        """
        property
        Sets the next Edge of the edge
        """
        self._next = value
        # check the size
        self.check_size()

    @property
    def face(self) -> Optional['Face']:
        """
        property
        :return: the face of the edge
        """
        return self._face

    @face.setter
    def face(self, value: Optional['Face']):
        """
        property
        Sets the face of the edge
        """
        self._face = value  # should be None for a boundary edge

    @property
    def space_next(self) -> Optional['Edge']:
        """
        property
        The next_space is the next edge on the space boundary
        :return: the next_space of the edge on the space boundary
        """
        return self._space_next

    @space_next.setter
    def space_next(self, value: Optional['Edge']):
        """
        property
        Sets the face of the edge
        """
        self._space_next = value

    @property
    def is_mutable(self):
        """
        Returns True if the edge can be split, False otherwise
        An edge can not be split if its link to an immutable linear (for example a window)
        :return:
        """
        if not self.linear:
            return True
        if self.linear.category.mutable:
            return True
        return False

    @property
    def is_space_boundary(self):
        """
        property
        :return:
        """
        return self.space_next is not None

    @property
    def space(self):
        """
        property
        :return: the space of the face of the edge
        """
        if self.face is None:
            return None
        return self.face.space

    @property
    def mesh(self):
        """
        Property
        The mesh the edge belongs to
        :return:
        """
        if self.face is not None:
            return self.face.mesh
        else:
            return self.pair.face.mesh

    @property
    def absolute_angle(self) -> float:
        """
        Returns the ccw angle in degrees between he (0,1) vector and the edge
        :return:
        """
        return ccw_angle(self.vector)

    @property
    def next_angle(self) -> float:
        """
        returns the counter clockwise angle between the next edge and this one
        :return: angle in degree
        """
        return ccw_angle(self.next.vector, self.opposite_vector)

    @property
    def previous_angle(self) -> float:
        """
        returns the counter clockwise angle in degrees
        between the edge and the previous one
        :return: angle in degree
        """
        return ccw_angle(self.vector, self.previous.opposite_vector)

    @property
    def next_is_outward(self) -> bool:
        """
        Specifies it the next edge is outward or inward
        :return: boolean
        """
        return self.next_angle > 180

    @property
    def next_is_aligned(self) -> bool:
        """
        Indicates if the next edge is approximately aligned with this one,
        using a pseudo equality on the angle
        :return: boolean
        """
        is_aligned = angle_pseudo_equal(self.next_angle, 180)
        return is_aligned

    @property
    def previous_is_aligned(self) -> bool:
        """
        Indicates if the next edge is approximately aligned with this one,
        using a pseudo equality on the angle
        :return: boolean
        """
        is_aligned = angle_pseudo_equal(self.previous_angle, 180)
        return is_aligned

    @property
    def next_is_ortho(self) -> bool:
        """
        Indicates if the next edge i
        :return:
        """
        return angle_pseudo_equal(self.next_angle, 90)

    @property
    def length(self) -> float:
        """
        Calculates the length of the edge
        :return: float the length of the edge
        """
        return self.start.distance_to(self.end)

    @property
    def opposite_vector(self) -> Vector2d:
        """
        Convenient function to calculate the opposite vector of the edge
        :return: tuple containing x, y values
        """
        return self.start.x - self.end.x, self.start.y - self.end.y

    @property
    def vector(self) -> Vector2d:
        """
        Convenient function to calculate the direction vector of the edge
        :return: tuple containing x, y values
        """
        return self.end.x - self.start.x, self.end.y - self.start.y

    @property
    def unit_vector(self) -> Vector2d:
        """
        Returns a unit vector with the same direction as the edge
        :return: vector of length 1
        """
        return normalized_vector(self.vector)

    @property
    def end(self) -> Optional[Vertex]:
        """
        Returns the vertex at the end of the edge,
        if the edge has no next edge : return None
        :return: vertex
        """
        if self.next is None:
            return None
        return self.next.start

    @property
    def previous(self) -> 'Edge':
        """
        Returns the previous edge by looping through the whole face.
        Will fail if the edge is not a member of a proper formed face.
        :return: edge
        """
        for edge in self.siblings:
            if edge.next is None:
                # Note : we could actually allow
                # this but I think this better for debugging purposes
                raise Exception('The face is badly formed :' +
                                ' one of the edge has not a next edge')
            if edge.next is self:
                return edge
        raise Exception('Not previous edge found !')

    @property
    def space_previous(self) -> 'Edge':
        """
        Returns the previous edge by looping through space boundary.
        Will fail if the edge is not a member of a proper formed Space.
        :return: edge
        """
        for edge in self.space_siblings:
            if edge.space_next is None:
                raise Exception('The face is badly formed :' +
                                ' one of the edge has not a next edge')
            if edge.space_next is self:
                return edge
        raise Exception('Not previous space edge found !')

    @property
    def ccw(self) -> 'Edge':
        """
        Returns the next edge starting from the same vertex as the edge.
        In counter clockwise order.
        :return: edge
        """
        return self.previous.pair

    @property
    def cw(self) -> 'Edge':
        """
        Returns the next edge starting from the same vertex as the edge.
        In clockwise order
        :return: edge
        """
        return self.pair.next

    @property
    def normal(self) -> Vector2d:
        """
        A CCW normal of the edge of length 1
        :return: a tuple containing x, y values
        """
        x, y = -self.vector[1], self.vector[0]
        length = math.sqrt(x**2 + y**2)
        return x/length, y/length

    @property
    def max_length(self) -> Optional[float]:
        """
        Returns the max length of the direction of the edge
        Totally arbitrary formula
        :return:
        """
        angle = self.absolute_angle % 180.0
        # we round the angle to the desired precision given by the ANGLE_EPSILON constant
        angle = np.round(angle / ANGLE_EPSILON) * ANGLE_EPSILON
        max_l = next((l for deg, l in self.mesh.directions if angle_pseudo_equal(deg, angle)), None)
        return (max_l / 2) * 1.10 if max_l is not None else None

    def sp_ortho_line(self, vertex) -> LineString:
        """
        Returns a shapely LineString othogonal
        to the edge starting from the vertex
        :param vertex:
        :return: shapely LineString
        """
        return vertex.sp_line(self.normal)

    @property
    def as_sp(self) -> LineString:
        """
        The edge as shapely LineString
        :return: shapely LineString
        """
        return LineString([self.start.as_sp, self.end.as_sp])

    @property
    def as_sp_extended(self) -> LineString:
        """
        Returns a slightly longer lineString
        (from both edges) in order to prevent near miss
        due to floating point precision
        :return:
        """
        vector = self.unit_vector
        end_point = move_point(self.end.coords, vector, COORD_EPSILON)
        start_point = move_point(self.start.coords, vector, -1*COORD_EPSILON)
        return LineString([start_point, end_point])

    @property
    def as_sp_dilated(self) -> Polygon:
        """
        Returns a dilated lineString to ensure snapping
        in order to prevent near miss due to floating point precision
        :return: a shapely Polygon
        """
        return self.as_sp.buffer(COORD_EPSILON, 1)

    @property
    def siblings(self) -> Generator['Edge', None, None]:
        """
        Returns the siblings of the edge, starting with itself
        :return: generator yielding each edge in the loop
        """
        yield self
        edge = self.next
        # in order to detect infinite loop we stored each yielded edge
        seen = []
        while edge is not self:
            if edge in seen:
                raise Exception('Infinite loop' +
                                ' starting from edge:{0}'.format(self))
            seen.append(edge)
            yield edge
            edge = edge.next

    @property
    def reverse_siblings(self) -> Generator['Edge', None, None]:
        """
        Returns the siblings of the edge, starting with itself
        looping in reverse
        :return: generator yielding each edge in the loop
        """
        yield self
        edge = self.previous
        # in order to detect infinite loop we stored each yielded edge
        seen = []
        while edge is not self:
            if edge in seen:
                raise Exception('Infinite loop' +
                                ' starting from edge:{0}'.format(self))
            seen.append(edge)
            yield edge
            edge = edge.previous

    @property
    def space_siblings(self) -> Generator['Edge', None, None]:
        """
        Returns the siblings of the edge on the space boundary,
        starting with itself
        :return: generator yielding each edge in the loop
        """
        yield self
        edge = self.space_next
        # in order to detect infinite loop we stored each yielded edge
        seen = []
        while edge is not self:
            if edge in seen:
                raise Exception('Infinite space loop' +
                                ' starting from edge:{0}'.format(self))
            seen.append(edge)
            yield edge
            edge = edge.space_next

    @property
    def aligned_siblings(self)-> Generator['Edge', None, None]:
        """
        Returns the edges that are aligned with self and contiguous
        Starts with the edge itself, then all the next ones, then all the previous ones
        :return:
        """
        yield self
        # forward check
        for edge in self.next.siblings:
            if not edge.previous_is_aligned:
                break
            yield edge
        # backward check
        for edge in self.previous.reverse_siblings:
            if not edge.next_is_aligned:
                break
            yield edge

    def is_linked_to_face(self, face: 'Face') -> bool:
        """
        Indicates if an edge is still linked to its face
        :param face:
        :return: boolean
        """
        if face.edge is self:
            return True
        for edge in self.siblings:
            if edge is face.edge:
                return True
        return False

    def is_linked_to_space(self, space) -> bool:
        """
        Indicates if an edge is still linked to its space
        :param space:
        :return: boolean
        """
        if space.face is self.face:
            return True
        for edge in self.space_siblings:
            if edge.face is space.face:
                return True
        return False

    def remove(self):
        """
        Removes the edge from the face. The corresponding faces are merged
        1. remove the face from the mesh
        2. stitch the extremities of the removed edge
        3. attribute correct face to orphan edges
        :return: mesh
        """
        other_face = self.pair.face

        # attribute new face to orphan
        # note if the edge is a boundary edge we attribute the edge face
        # to the pair edge siblings, not the other way around
        if self.face is not None:
            self.face.remove_from_mesh()
            for edge in self.siblings:
                edge.face = other_face
        else:
            other_face.remove_from_mesh()
            for edge in self.pair.siblings:
                edge.face = self.face

        # preserve references
        self.preserve_references()
        self.pair.preserve_references()

        # stitch the edge extremities
        self.pair.previous.next = self.next
        self.previous.next = self.pair.next

        # clean useless vertices
        self.start.clean()
        self.end.clean()

    def preserve_references(self, other: Optional['Edge'] = None):
        """
        Used to preserve face, vertex and boundary references
        when the edge is removed from the mesh.
        A mesh is considered removed from a mesh if there an't anymore
        edge pointers to it and its pair.
        """
        # preserve face reference
        if self.face and self.face.edge is self:
            self.face.edge = other or self.next

        # preserve boundary edge reference
        if self is self.mesh.boundary_edge:
            self.mesh.boundary_edge = other or self.next

        # preserve vertex reference
        if self.start.edge is self:
            self.start.edge = other or self.ccw

        # preserve space reference
        if self.space is not None and self.space.edge is self:
            self.space.edge = other or self.space_next

        # preserve linear reference
        if self.linear is not None and self.linear.edge is self:
            self.linear.edge = other or self.space_next

    def intersect(self, vector: Vector2d, max_length: Optional[float] = None) -> Optional['Edge']:
        """
        Finds the opposite point of the edge end on the face boundary
        according to a vector direction.
        A vertex is created at the corresponding point by splitting the edge.
        Returns the edge created at the intersection vertex,
        before the intersection.
        :param vector:
        :param max_length: maximum authorized length of the cut
        :return: the laser_cut edge
        """

        intersection_data = self.end.project_point(self.face, vector)

        # if not intersection was found we return None
        if intersection_data is None:
            return None

        intersection_vertex, closest_edge, distance_to_edge = intersection_data

        # check if we've exceeded the max authorized length
        if max_length is not None and max_length < distance_to_edge:
            return None

        # split the destination edge
        closest_edge = closest_edge.split(intersection_vertex)

        # if the destination edge cannot be split return None
        return closest_edge.previous if closest_edge else None

    def link(self, other: 'Edge') -> Optional['Edge']:
        """
        Creates an edge between two edges.
        We link the end vertices of each edge
        Note : we cannot linked two edges that are already linked
        (that are the next edge of each other)
        :param other: the edge to link to
        :return: the created edge or None if the edge can not be linked
        """
        # check if the edges are already linked
        if other.next is self or self.next is other:
            logging.warning('cannot link two edges ' +
                            ' that are already linked:{0}-{1}'.format(self, other))
            return None

        # check if the edges are the same
        if other is self or self.end is other.end:
            logging.warning('cannot link one vertex to itself ' +
                            ':{0}-{1}'.format(self, other))
            return None

        # create the new edge and its pair
        new_edge = Edge(self.end, other.next, self.face)
        new_edge.pair.start = other.end
        new_edge.pair.next = self.next

        # create a new face
        new_face = Face(new_edge.pair, self.mesh, other.face.space)
        new_edge.pair.face = new_face

        # modify initial edges next edges to follow the laser_cut
        self.next = new_edge
        other.next = new_edge.pair

        # assign all the edges from one side of the laser_cut to the new face
        for edge in new_edge.pair.siblings:
            edge.face = new_face

        return new_edge

    def laser_cut(self,
                  vertex: Vertex,
                  angle: float = 90.0,
                  traverse: str = 'absolute',
                  vector: Optional[Vector2d] = None,
                  max_length: Optional[float] = None,
                  callback: Optional[SpaceCutCb] = None) -> Optional[Tuple['Edge', 'Edge']]:
        """
        Will laser_cut a face from the edge at the given vertex
        following the given angle or the given vector
        :param vertex: where to laser_cut the edge
        :param angle : indicates the angle to laser_cut the face from the vertex
        :param traverse: String indicating if we must keep cutting the next face and how.
        Possible values : 'absolute', 'relative'
        :param vector: a vector indicating the absolute direction fo the laser_cut,
        if present we ignore the angle parameter
        :param max_length: max length for the total laser_cut
        :param callback: Optional
        :return: self
        """
        # do not cut an edge on the boundary
        if self.face is None:
            return None

        # a relative angle or a vector
        # can be provided as arguments of the method
        if vector is not None:
            angle = ccw_angle(self.vector, vector)
        else:
            vector = unit_vector(ccw_angle(self.vector) + angle)

        # try to cut the edge
        new_edges = self.cut(vertex, angle, vector=vector, max_length=max_length)

        # if the vertex is at the end or the start of the edge
        # we have to try to cut the other edge starting
        # or ending to the same vertex
        if vertex is self.start:
            edge = self
            while new_edges is None and edge.ccw is not self:
                new_edges = self.ccw.cut(vertex, vector=vector, max_length=max_length)
                edge = edge.ccw

        if vertex is self.end:
            edge = self
            while new_edges is None and edge.pair.cw.pair is not self:
                new_edges = self.pair.cw.pair.cut(vertex, vector=vector, max_length=max_length)
                edge = edge.pair.cw.pair

        if new_edges is None:
            return None

        new_edge_start, new_edge_end = new_edges

        # call the callback
        stop = False
        if callback is not None:
            stop = callback(new_edges)

        # check the distance
        if max_length is not None:
            distance_traveled = new_edge_start.start.distance_to(new_edge_end.start)
            max_length -= distance_traveled

        # laser_cut the next edge if traverse option is set
        if traverse == 'absolute' and not stop:
            return new_edge_end.pair.laser_cut(new_edge_end.start, angle, vector=vector,
                                               max_length=max_length, callback=callback)

        if traverse == 'relative' and not stop:
            return new_edge_end.pair.laser_cut(new_edge_end.start, angle, traverse='relative',
                                               max_length=max_length, callback=callback)

        return new_edges

    def cut(self,
            vertex: Vertex,
            angle: float = 90.0,
            vector: Optional[Vector2d] = None,
            max_length: Optional[float] = None) -> Optional[Tuple['Edge', 'Edge']]:
        """
        Will cut a face from the edge at the given vertex
        following the given angle or the given vector
        :param vertex: where to laser_cut the edge
        :param angle : indicates the angle to laser_cut the face from the vertex
        :param vector: a vector indicating the absolute direction fo the laser_cut,
        if present we ignore the angle parameter
        :param max_length : the max_length authorized for the cut
        :return: the new created edges
        """

        # do not cut an edge on the boundary
        if self.face is None:
            return None

        first_edge = self

        # a relative angle or a vector
        # can be provided as arguments of the method
        if vector is not None:
            angle = ccw_angle(self.vector, vector)

        # snap vertex if they are very close to the end or the start of the edge
        vertex = vertex.snap_to(self.start, self.end)

        # check for extremity cases
        # 1. the vertex is the start of the edge
        if vertex is self.start:
            angle_is_inside = MIN_ANGLE < angle < self.previous_angle - MIN_ANGLE
            if not angle_is_inside:
                logging.info('Cannot cut according to angle:{0} < {1} < {2}'.
                             format(MIN_ANGLE, angle, self.previous_angle - MIN_ANGLE))
                return None

            first_edge = self.previous
        # 2. the vertex is the end of the edge
        elif vertex is self.end:
            angle_is_inside = 180 - MIN_ANGLE > angle > 180.0 - self.next_angle + MIN_ANGLE
            if not angle_is_inside:
                logging.info('Cannot cut according to angle:{0} > {1} > {2}'.
                             format(180 - MIN_ANGLE, angle, 180.0 - self.next_angle + MIN_ANGLE))
                return None
        else:
            # split the starting edge
            first_edge.split(vertex)
            # do not cut an edge that is not mutable
            if not self.is_mutable:
                logging.info('Could not a cut an immutable linear:' +
                             '{0}'.format(self.linear.category.name))
                return None

        # create a line to the edge at the vertex position
        line_vector = vector if vector is not None else unit_vector(ccw_angle(self.vector) + angle)
        closest_edge = first_edge.intersect(line_vector, max_length)

        # if no intersection can be found return None
        if closest_edge is None:
            logging.info('Could not create a viable cut')
            return None

        # assign a correct edge to the initial face
        # (to ensure that its edge is still included in the face)
        first_edge.face.edge = first_edge

        # per convention we return the two edges starting
        # from the cut vertex and the intersection vertex
        closest_edge_next = closest_edge.next
        first_edge_next = first_edge.next

        # link the two edges
        link_edge = first_edge.link(closest_edge)
        # check to see if the link was properly executed.
        # if not, it means that the closest edge was linked to the first edge
        # to prevent recursion while laser cutting if the first_edge is the closest_edge next edge
        # we return a different edge as the next edge to cut
        if link_edge is None:
            if closest_edge.next is first_edge:
                closest_edge_next = first_edge.pair.next

        return first_edge_next, closest_edge_next

    def laser_cut_at_barycenter(self, coeff: float,
                                angle: float = 90.0) -> Optional[Tuple['Edge', 'Edge']]:
        """
        Laser cuts an edge according to the provided angle (90° by default)
        and at the barycentric position
        :param coeff:
        :param angle:
        :return:
        """
        vertex = Vertex().barycenter(self.start, self.end, coeff)
        return self.laser_cut(vertex, angle)

    def cut_at_barycenter(self, coeff: float = 0.5,
                          angle: float = 90.0) -> Optional[Tuple['Edge', 'Edge']]:
        """
        Cuts an edge according to the provided angle (90° by default)
        and at the barycentric position
        :param coeff:
        :param angle:
        :return:
        """
        vertex = Vertex().barycenter(self.start, self.end, coeff)
        return self.cut(vertex, angle)

    def split(self, vertex: 'Vertex') -> Optional['Edge']:
        """
        Splits the edge at a specific vertex
        :param vertex: a vertex object where we should split
        :return: the newly created edge starting from the vertex
        """
        # check for vertices proximity and snap if needed
        vertex = vertex.snap_to(self.start, self.end)

        # check extremity cases : if the vertex is one of the extremities of the edge do nothing
        if vertex is self.start:
            return self
        if vertex is self.end:
            return self.next

        # check for immutable edge
        # (we check after snapping because an immutable edge can be split at its extremities)
        if not self.is_mutable:
            return None

        # define edges
        edge = self
        next_edge = self.next
        edge_pair = self.pair
        edge_pair_previous = self.pair.previous

        # create a new edge and assign it to vertex if needed
        new_edge = Edge(vertex, next_edge, edge.face)
        new_edge.pair.face = edge_pair.face
        new_edge.pair.start = edge_pair.start
        vertex.edge = vertex.edge if vertex.edge is not None else new_edge

        # insure correct vertex reference
        if edge_pair.start.edge is edge_pair:
            edge_pair.start.edge = new_edge.pair

        # change the current edge destinations and starting point
        edge_pair_previous.next = new_edge.pair
        edge_pair.start = vertex
        edge.next = new_edge
        new_edge.pair.next = edge_pair

        # preserve space boundary pointer [SPACE]
        if edge.is_space_boundary:
            new_edge.space_next = edge.space_next
            edge.space_next = new_edge
        if edge_pair.is_space_boundary:
            edge_pair.space_previous.space_next = new_edge.pair
            new_edge.pair.space_next = edge_pair

        # preserve linear pointer [LINEAR]
        new_edge.linear = edge.linear

        return new_edge

    def split_barycenter(self, coeff: float) -> 'Edge':
        """
        Splits the edge at the provided barycentric position. A vertex is created.
        :param coeff: float
        :return: self
        """
        vertex = Vertex().barycenter(self.start, self.end, coeff)
        return self.split(vertex)

    def plot_half_edge(self, ax, color: str = 'black', save: Optional[bool] = None):
        """
        Plots a semi-arrow to indicate half-edge for debugging purposes
        :param ax:
        :param color:
        :param save: whether to save the plot
        :return:
        """
        arrow = make_arrow(self.start.coords, self.vector, self.normal)
        x_coords, y_coords = zip(*arrow.coords)
        return plot_edge(x_coords, y_coords, ax, color=color, save=save)

    def plot_normal(self, ax, color: str = 'black'):
        """
        Plots the normal vector of the edge for debugging purposes
        :param ax:
        :param color:
        :return:
        """
        start_point = barycenter(self.start.coords, self.end.coords, 0.5)
        arrow = self.normal
        # noinspection PyCompatibility
        ax.quiver(*start_point, *arrow, color=color)

        return ax

    def check_size(self):
        """Checks the size of the edge"""
        if self.start and self.end and self.start is self.end:
            raise ValueError('Cannot create and edge starting and ending with the same' +
                             'vertex: {0}'.format(self.start))

        if self.start and self.end and self.length < COORD_EPSILON:
            logging.warning('Created a very small edge: {0} - {1}'.format(self.start, self.end))


class Face:
    """
    Face Class
    """
    def __init__(self,
                 edge: Optional[Edge],
                 enclosing_mesh: Optional['Mesh'] = None,
                 space=None):
        # any edge of the face
        self._edge = edge
        self._mesh = enclosing_mesh
        self._space = space
        # add new face to mesh
        if enclosing_mesh is not None:
            enclosing_mesh.add_face(self)

    def __repr__(self):
        output = 'Face: ['
        for edge in self.edges:
            output += '({0}, {1})'.format(*edge.start.coords)
        return output + ']'

    @property
    def edge(self) -> Edge:
        """
        property
        :return: the edge of the face
        """
        return self._edge

    @edge.setter
    def edge(self, value: Edge):
        """
        property
        Sets the edge of the face
        """
        self._edge = value

    @property
    def mesh(self) -> 'Mesh':
        """
        property
        :return: the mesh of the face
        """
        return self._mesh

    @mesh.setter
    def mesh(self, value: 'Mesh'):
        """
        property
        Sets the mesh of the face
        """
        self._mesh = value

    @property
    def space(self):
        """
        property
        :return: the space of the face
        """
        return self._space

    @space.setter
    def space(self, value):
        """
        property
        Sets the space of the face
        """
        self._space = value

    @property
    def edges(self, from_edge: Optional[Edge] = None) -> Generator[Edge, None, None]:
        """
        Loops trough all the edges belonging to a face.
        We start at the edge stored in the face and follow each edge next until
        a full loop has been accomplished.
        NB: if the edges of the face do not form a proper loop
        the method will fail or loop for ever
        :param from_edge: from which edge of the face the loop starts
        :return: a generator
        """
        edge = from_edge or self.edge
        yield from edge.siblings

    @property
    def vertices(self) -> Generator[Vertex, None, None]:
        """
        Lists the vertices on the edges of the face
        :return: Generator
        """
        return (edge.start for edge in self.edges)

    @property
    def as_sp(self) -> Polygon:
        """
        Returns a shapely Polygon corresponding to the face geometry
        :return: Polygon
        """
        list_vertices = [vertex.coords for vertex in self.vertices]
        list_vertices.append(list_vertices[0])
        return Polygon(list_vertices)

    def as_sp_linear_ring(self) -> LinearRing:
        """
        Returns a shapely LinearRing corresponding to the face perimeter
        :return: LinearRing
        """
        list_vertices = [vertex.coords for vertex in self.vertices]
        return LinearRing(list_vertices)

    @property
    def as_sp_dilated(self) -> Polygon:
        """
        Returns a dilated Polygon corresponding to the face with a small buffer
        This is useful to prevent floating point precision errors.
        :return: Polygon
        """
        return self.as_sp.buffer(COORD_EPSILON, 1)

    @property
    def area(self) -> float:
        """
        Calculates and returns the area of the face
        We use the shapely module to compute the area
        :return: float
        """
        return self.as_sp.area

    @property
    def length(self) -> float:
        """
        Calculates the perimeter length of the face
        We use the shapely module to compute the perimeter
        :return: float
        """
        return self.as_sp.length

    def add_to_mesh(self, mesh: 'Mesh') -> 'Face':
        """
        Adds the face to a mesh
        :param mesh:
        :return: face
        """
        mesh.add_face(self)
        return self

    def remove_from_mesh(self):
        """
        Removes the face reference from the mesh
        :return: None
        """
        mesh = self.mesh
        if mesh is None:
            raise ValueError('Face has no mesh to remove it from: {0}'.format(self))
        mesh.remove_face(self)

    def get_edge(self, vertex: Vertex) -> Optional[Edge]:
        """
        Retrieves the half edge of the face starting with the given vertex.
        Returns None if no edge is found.
        :param vertex:
        :return: edge
        """
        for edge in self.edges:
            if edge.start is vertex:
                return edge
        return None

    def contains(self, other: 'Face') -> bool:
        """
        Indicates if the face contains another face.
        We use a dilated face in order to prevent floating point decimal errors
        :param other:
        :return:
        """
        return self.as_sp_dilated.contains(other.as_sp)

    def add_exterior(self, other: 'Face') -> 'Face':
        """
        Assigns to the external edge the provided face.
        Useful before inserting a face inside another
        :param other: face
        :return: self
        """
        for edge in self.edge.pair.siblings:
            edge.face = other

        return self

    def _insert_enclosed_face(self, face: 'Face') -> List['Face']:
        """
        Insert a fully enclosed face inside a containing face
        Note: this method should always be called from insert_face
        1. select a vertex from the face
        2. find the nearest point on the perimeter of the containing face
        3. split the edge on the nearest point
        4. create the edge between the two point
        5. assign pair faces
        :param face:
        :return:
        """
        # create a fixed list of the enclosing face edges for ulterior navigation
        main_directions = self.mesh.directions
        vectors = unit_vector(main_directions[0][0]), unit_vector(main_directions[1][0])

        # find the closest vertex of the face to the boundary of the receiving face
        # according to the mesh two main directions
        min_distance = None
        best_vertex = None
        best_near_vertex = None
        best_shared_edge = None
        for vertex in face.vertices:
            for vector in vectors:
                _correct_orientation = not same_half_plane(vector, vertex.edge.vector)
                _vector = vector if _correct_orientation else opposite_vector(vector)
                intersection_data = vertex.project_point(self, _vector)
                if intersection_data is None:
                    continue
                near_vertex, shared_edge, distance_to_vertex = intersection_data
                # check whether we are projecting unto an immutable linear
                if not shared_edge.is_mutable:
                    continue
                if min_distance is None or distance_to_vertex < min_distance:
                    best_vertex = vertex
                    best_near_vertex = near_vertex
                    best_shared_edge = shared_edge
                    min_distance = distance_to_vertex

        if min_distance is None:
            raise Exception('Cannot find and intersection point to insert face !:{0}'.format(face))

        # create a new edge linking the vertex of the face to the enclosing face
        edge_shared = best_near_vertex.snap_to_edge(best_shared_edge)
        best_near_vertex = edge_shared.start  # ensure existing vertex reference
        new_edge = Edge(best_near_vertex, best_vertex.edge.previous.pair, self)
        new_edge.pair.face = self
        new_edge.pair.start = best_vertex
        best_near_vertex.edge = new_edge
        new_edge.pair.next = edge_shared
        edge_shared.previous.next = new_edge
        best_vertex.edge.pair.next = new_edge.pair

        return [self]

    def _insert_touching_face(self, shared_edges: Sequence[Tuple[Edge, Edge]]) -> List['Face']:
        """
        Inserts a face inside another when the inserted face has one or several touching points
        with the container face. A "stitching" algorithm is used.

        WARNING : Because the inserted face touches the container face,
        this can lead to the creation of several new faces.
        Because of the way the algorithm is coded it can even lead to the
        disappearance of the initial container face from the mesh.
        In order to enable the user to preserve references to the initial container face
        (for example if other faces need to be inserted) the biggest face is returned.

        ex: new_container_face = container_face.insert(face_to_insert)

        :param shared_edges:
        :return: the largest faces created inside self
        """

        touching_edge, edge, new_face = None, None, None
        # NB: touching_edge is the edge on the container face
        all_faces = [self]

        # connect the edges together
        for shared in shared_edges:
            touching_edge, edge = shared
            previous_edge = edge.previous
            previous_touching_edge = touching_edge.previous

            # connect the correct edges
            previous_touching_edge.next = previous_edge.pair
            edge.pair.next = touching_edge

            # insure proper face edge reference
            self.edge = touching_edge

            # backward check for isolation
            # first check for 2-edged face
            # if a 2 edged face is found we keep the edge and remove the touching edge
            if previous_edge.pair.next.next is previous_edge.pair:
                # preserve references for space, linear, face and vertex
                previous_edge.pair.preserve_references(previous_edge.pair.next.pair)
                previous_edge.pair.next.preserve_references(previous_edge)
                # remove the duplicate edges
                previous_edge.pair = previous_edge.pair.next.pair

                # [SPACE] keep space boundary references
                if previous_touching_edge.is_space_boundary:
                    previous_touching_edge.space_previous.space_next = previous_edge
                    previous_edge.space_next = previous_touching_edge.space_next

            # else check for new face creation
            elif not previous_edge.pair.is_linked_to_face(self):
                new_face = Face(previous_edge.pair, self.mesh)
                new_face.space = self.space  # [SPACE]
                all_faces.append(new_face)
                for orphan_edge in previous_edge.pair.siblings:
                    orphan_edge.face = new_face

        # forward check : at the end of the loop check forward for isolation
        if edge.pair.next.next is edge.pair:
            edge.pair = touching_edge.pair
            # [SPACE] keep space references
            if touching_edge.is_space_boundary:
                touching_edge.space_previous.space_next = edge
                edge.space_next = touching_edge.space_next
            # remove face from edge
            self.remove_from_mesh()  # Note : this is problematic for face absolute reference
            all_faces.pop(0)  # remove self from the list of all the faces

        # return the biggest face first per convention
        sorted_faces = sorted(all_faces, key=attrgetter('area'), reverse=True)
        return sorted_faces

    def _insert_identical_face(self, face):
        """
        insert a identical face
        :param face:
        :return:
        """
        print('The inserted face is equal to the container face,' +
              ' no need to do anything: {0}'.format(face))
        return [self]  # NOTE : not sure this is best. Maybe we should swap self with face

    def insert_face(self, face: 'Face') -> List['Face']:
        """
        Inserts the face if it fits inside the receiving face
        Returns the list of the faces created inside the receiving face

        """
        if not self.contains(face):
            raise ValueError("Cannot insert a face that is not" +
                             " entirely contained in the receiving face !:{0}".format(face))

        # add the new face to the mesh
        self.mesh.add_face(face)

        # add all pair edges to face
        face.add_exterior(self)

        # create a fixed list of the face edges for ulterior navigation
        self_edges = list(self.edges)

        # add the space reference [SPACE]
        face.space = self.space

        # split the face edges if they touch a vertex of the container face
        # TODO : this is highly inefficient as we try to intersect every edge with every vertex

        for vertex in self.vertices:
            face_edges = list(face.edges)
            vertex.snap_to_edge(*face_edges)

        # snap face vertices to edges of the container face
        # for performance purpose we store the snapped vertices and the corresponding edge
        shared_edges = []
        face_edges = list(face.edges)
        for edge in face_edges:
            vertex = edge.start
            edge_shared = vertex.snap_to_edge(*self_edges)
            if edge_shared is not None:
                shared_edges.append((edge_shared, edge))
                # after a split: update list of edges
                self_edges = list(self.edges)

        nb_shared_vertices = len(shared_edges)

        # different use cases
        # case 1 : enclosed face
        if nb_shared_vertices == 0:
            return self._insert_enclosed_face(face)
        # case 2 : same face
        if nb_shared_vertices == len(self_edges):
            return self._insert_identical_face(face)
        # case 3 : touching face
        return self._insert_touching_face(shared_edges)

    def insert_face_from_boundary(self, perimeter: List[Coords2d]) -> List['Face']:
        """
        Insertes a face directly from a boundary
        :param perimeter:
        :return: the biggest face
        """

        mesh = Mesh().from_boundary(perimeter)
        face_to_insert = mesh.faces[0]
        return self.insert_face(face_to_insert)

    def is_linked_to_space(self):
        """
        Returns True if the face is linked to the Space
        This has the meaning that the face is connected to the reference face of the Space.
        :return:
        """

        if self.space is None:
            return True  # per convention

        if self.space.face is self:
            return True

        for face in self.space.faces:
            if face is self:
                return True

        return False

    def insert_edge(self, vertex_1: Vertex, vertex_2: Vertex):
        """
        Inserts an edge on the boundary of the face
        :param vertex_1:
        :param vertex_2:
        :return:
        """
        edges = []
        for vertex in vertex_1, vertex_2:
            edge = vertex.snap_to_edge(*self.edges)
            if edge is None:
                logging.warning('Could not insert edge because vertex is not on the face boundary')
                return None
            edges.append(edge)

        return edges[0]

    def plot(self,
             ax=None,
             options=('fill', 'border'),
             color: Optional[str] = None,
             save: Optional[bool] = None):
        """
        Plots the face
        :return:
        """
        x, y = self.as_sp.exterior.xy
        return plot_polygon(ax, x, y, options, color, save)


class Mesh:
    """
    Mesh Class
    """
    def __init__(self, faces: Optional[List[Face]] = None, boundary_edge: Optional[Edge] = None):
        self._faces = faces
        self._boundary_edge = boundary_edge

    def __repr__(self):
        output = 'Mesh:\n'
        for face in self.faces:
            output += face.__repr__() + '\n'
        return output + '-'*24

    @property
    def faces(self) -> List[Face]:
        """
        property
        :return: the faces of the mesh
        """
        return self._faces

    @faces.setter
    def faces(self, value: List[Face]):
        """
        property
        Sets the faces of the mesh
        """
        self._faces = value

    @property
    def boundary_edge(self) -> Edge:
        """
        property
        :return: one of the external edge of the mesh
        """
        return self._boundary_edge

    @boundary_edge.setter
    def boundary_edge(self, value: Edge):
        """
        property
        Sets the external edge of the mesh
        """
        if value.face is not None:
            raise ValueError('An external edge cannot have a face: {0}'.format(value))
        self._boundary_edge = value

    @property
    def boundary_edges(self):
        """
        Generator to retrieve all the external edges of the mesh
        :return: generator
        """
        if self.boundary_edge is None:
            raise ValueError('An external edge must be specified for this mesh !')

        yield from self.boundary_edge.siblings

    @property
    def directions(self) -> Sequence[Tuple[float, float]]:
        """
        Returns the main directions of the mesh.
        For each boundary edge we calculate the absolute ccw angle and we add it to a dict.
        :return:
        """
        directions_dict = {}

        for edge in self.boundary_edges:
            angle = edge.absolute_angle % 180.0
            # we round the angle to the desired precision given by the ANGLE_EPSILON constant
            angle = np.round(angle / ANGLE_EPSILON) * ANGLE_EPSILON
            if angle in directions_dict:
                directions_dict[angle] += edge.length
            else:
                directions_dict[angle] = edge.length

        return sorted(directions_dict.items(), key=itemgetter(1), reverse=True)

    def add_face(self, face: Face) -> 'Mesh':
        """
        Adds a face to the mesh
        :param face:
        :return: self
        """
        face.mesh = self
        if self.faces is None:
            self.faces = [face]
        else:
            self.faces.append(face)
        return self

    def remove_face(self, face: Face):
        """
        Removes from the mesh the face
        :param face:
        :return: self
        """
        if face not in self.faces:
            raise ValueError('Cannot remove the face that' +
                             ' is not already in the mesh, {0}'.format(face))
        self.faces.remove(face)

    def check(self) -> bool:
        """
        Checks if the mesh is correctly formed.
        It's a best effort. Only a few strong consistencies are checked.
        :return: boolean
        """
        is_valid = True
        for face in self.faces:
            for edge in face.edges:
                if edge is None:
                    is_valid = False
                    logging.error('Checking Mesh: Edge is None for:{0}'.format(face))
                if edge.face is not face:
                    is_valid = False
                    logging.error('Checking Mesh: Wrong face in edge:' +
                                  '{0} for face:{1}'.format(edge, edge.face))
                if edge.pair and edge.pair.pair is not edge:
                    is_valid = False
                    logging.error('Checking Mesh: Wrong pair attribution:' +
                                  ' {0} for face: {1}'.format(edge, edge.pair))
                if edge.start.edge is None:
                    is_valid = False
                    logging.error('Checking Mesh: Vertex has no edge: {0}'.format(edge.start))
                if edge.start.edge.start is not edge.start:
                    is_valid = False
                    logging.error('Checking Mesh: Wrong edge attribution in: ' +
                                  '{0}'.format(edge.start))
                if edge.next.next is edge:
                    is_valid = False
                    logging.error('Checking Mesh: 2-edges face found:{0}'.format(face))
        for edge in self.boundary_edges:
            if edge.face is not None:
                logging.error('Wrong edge in mesh boundary edges:{0}'.format(edge))
        logging.info('Checking Mesh: ' + 'OK' if is_valid else '!! NOT OK')
        return is_valid

    # noinspection PyCompatibility
    def plot(self,
             ax=None,
             options=('fill', 'border', 'half-edges', 'boundary-edges', 'vertices'),
             save: bool = True,
             show: bool = False):
        """
        Plots a mesh using matplotlib library.
        A few options can be used:
        • 'fill' : add color to each face
        • 'edges' : outline each edge
        • 'normals' : display each half-edge normal vector. Useful for debugging.
        • 'half-edge': display arrows for each oriented half-edge. Useful for debugging.
        :param ax:
        :param options:
        :param save: whether to save as .svg file
        :param show: whether to show as matlplotlib window
        :return: ax
        """

        for face in self.faces:
            color = random_color()
            ax = face.plot(ax, options, color, False)

            for edge in face.edges:
                # display edges normal vector
                if 'normals' in options:
                    edge.plot_normal(ax, color)
                # display half edges vector
                if 'half-edges' in options:
                    edge.plot_half_edge(ax, color, False)

        if 'boundary-edges' in options:
            color = random_color()
            for edge in self.boundary_edges:
                edge.plot_half_edge(ax, color, False)

        plot_save(save, show)

        return ax

    def from_boundary(self, boundary: Sequence[Tuple[float, float]]) -> 'Mesh':
        """
        Creates a mesh object with one face from a list of points. We use a CCW rotation.
        Each point is a tuple of x, y coordinates
        Note : the boundary has to be in CCW order and the boundary can not cross itself.
        :param boundary: list of coordinates tuples
        :return: a Mesh object
        """
        # check if the perimeter respects the ccw rotation
        # we use shapely LinearRing object
        sp_perimeter = LinearRing(boundary)
        if not sp_perimeter.is_ccw:
            raise ValueError('The perimeter is not ccw:{0}'.format(boundary))
        if not sp_perimeter.is_simple:
            raise ValueError('The perimeter crosses itself:{0}'.format(boundary))

        initial_face = Face(None, self)
        initial_vertex = Vertex(boundary[0][0], boundary[0][1])
        initial_edge = Edge(initial_vertex, None, initial_face)

        self.boundary_edge = initial_edge.pair
        initial_face.edge = initial_edge
        initial_vertex.edge = initial_edge

        next_edge = initial_edge

        # we traverse the perimeter backward
        for i, point in enumerate(boundary[::-1]):
            # for the last item we loop on the initial edge
            if i == len(boundary) - 1:
                initial_edge.next = next_edge
                next_edge.pair.next = initial_edge.pair
                initial_edge.pair.start = next_edge.start
                break
            # create a new vertex
            vertex = Vertex(point[0], point[1])
            # create a new edge starting from this vertex
            current_edge = Edge(vertex, next_edge, initial_face)
            current_edge.pair.start = next_edge.start
            next_edge.pair.next = current_edge.pair
            # add the edge to the vertex
            vertex.edge = current_edge
            next_edge = current_edge

        return self


if __name__ == '__main__':

    logging.getLogger().setLevel(logging.INFO)

    def plot():
        """
        Plot a graph
        :return:
        """
        perimeter = [(0, 0), (200, 0), (200, 200), (100, 200), (100, 100), (0, 100)]
        mesh = Mesh().from_boundary(perimeter)

        for edge in mesh.boundary_edges:
            if edge.pair.next_is_outward:
                edge.pair.laser_cut_at_barycenter(1)
                edge.previous.pair.laser_cut_at_barycenter(0)

        mesh.plot(show=True)

    # plot()

    def remove_edge():
        """
        Test
        :return:
        """
        perimeter = [(0, 0), (200, 0), (200, 200), (100, 200), (100, 100), (0, 100)]
        mesh = Mesh().from_boundary(perimeter)

        edges = list(mesh.faces[0].edges)

        edges[0].laser_cut_at_barycenter(0.5)
        edges[3].laser_cut_at_barycenter(0.5)

        mesh.plot(show=True)

        edges = list(mesh.faces[0].edges)
        edges[1].remove()

        mesh.plot(show=True)

        edges = list(mesh.faces[1].edges)
        edges[0].remove()

        print(mesh.directions)

        mesh.check()
        mesh.plot(show=True, save=False)
        plt.show()

    remove_edge()