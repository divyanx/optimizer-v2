# coding=utf-8
"""
Mesh module
Half-edge representation
"""

import math
import logging
import uuid
from operator import attrgetter, itemgetter
from typing import Tuple, List, Sequence, Generator, Callable, Dict, Union, Optional
import enum

from shapely.geometry.polygon import Polygon
from shapely.geometry import Point, LineString, LinearRing

import libs.mesh.transformation as transformation
from libs.utils.custom_exceptions import OutsideFaceError, OutsideVertexError
from libs.utils.custom_types import Vector2d, SpaceCutCb, Coords2d, TwoEdgesAndAFace
from libs.utils.geometry import magnitude, ccw_angle
from libs.utils.geometry import (
    unit_vector,
    unit,
    barycenter,
    move_point,
    opposite_vector,
    pseudo_equal,
    dot_product,
    normal_vector,
    truncate,
    distance,
    project_point_on_segment
)
from libs.read_write.plot import random_color, make_arrow, plot_polygon, plot_edge, plot_save

# MODULE CONSTANTS

# arbitrary value for the length of the line :
# it should be long enough to approximate infinity
LINE_LENGTH = 50000000
ANGLE_EPSILON = 2.0  # value to check if an angle has a specific value
COORD_EPSILON = 1.0  # coordinates precision for snapping purposes
MIN_ANGLE = 5.0  # min. acceptable angle in grid
COORD_DECIMAL = 4  # number of decimal of the points coordinates
INFINITY = 2 ** 63 - 1


class MeshOps(enum.Enum):
    """
    A simple enum for mesh operations on mesh component
    """
    ADD = "added"
    REMOVE = "removed"
    INSERT = "Insert"


class MeshComponentType(enum.Enum):
    """
    A simple enum for mesh components
    """
    UNDEFINED = "Undefined"
    VERTEX = "Vertex"
    EDGE = "Edge"
    FACE = "Face"


class MeshComponent:
    """
    An abstract class for mesh component : vertex, edge or face
    """

    type = MeshComponentType.UNDEFINED

    __slots__ = '_id', '_mesh'

    def __init__(self, mesh: 'Mesh', _id: Optional[int] = None):
        self._id = _id
        self._mesh = mesh
        mesh.add(self)

    @property
    def id(self) -> int:
        """
        property
        returns the id of the vertex
        :return:
        """
        return self._id

    @id.setter
    def id(self, value: int):
        """
        Sets the id
        :param value:
        :return:
        """
        self._id = value

    def swap_id(self, other: 'MeshComponent'):
        """
        Swaps the id with the other component
        :param other:
        :return:
        """
        self.id, other.id = other.id, self.id
        self.mesh.update(other)
        self.mesh.update(self)

    @property
    def mesh(self) -> 'Mesh':
        """
        Property
        returns the mesh of the vertex
        :return:
        """
        return self._mesh

    @mesh.setter
    def mesh(self, value: 'Mesh'):
        """
        Sets the mesh of the vertex
        :param value:
        :return:
        """
        self._mesh = value
        if value is not None:
            value.add(self)

    def __hash__(self):
        # Note : this is incorrect in the sense that two edges from two different meshes
        # could have the same id. But this is faster and we are not comparing
        # edges from different meshes.
        return self.id

    def __eq__(self, other):
        if other is None:
            return False
        return self.id == other.id

    def __ne__(self, other):
        return not (self == other)

    def remove_from_mesh(self):
        """
        Removes the component from the mesh
        :return:
        """
        if not self._mesh:
            logging.warning('Component has no mesh to remove it from: {0}'.format(self))
            return
        self._mesh.remove(self)

    def add_to_mesh(self, mesh: 'Mesh', _id: Optional[int] = None):
        """
        Add the component to the mesh. If an id is provided it will be kept.
        Beware badly used this could induce pb.
        :return:
        """
        if _id is not None:
            assert _id not in mesh.components_id, "Mesh: Cannot add a component with this id"
        self._id = _id
        self._mesh = mesh
        self._mesh.add(self)

# Types for typing


MeshComponentIdTuple = Tuple[MeshComponentType, int]
MeshModification = Tuple[MeshOps, MeshComponentIdTuple, Optional[MeshComponentIdTuple]]


class Vertex(MeshComponent):
    """
    Vertex class
    """

    type = MeshComponentType.VERTEX

    __slots__ = '_x', '_y', '_edge', 'mutable'

    def __init__(self,
                 mesh: 'Mesh',
                 x: float = 0,
                 y: float = 0,
                 edge: 'Edge' = None,
                 mutable: bool = True,
                 _id: Optional[int] = None):
        """
        A simple Vertex class with barycentric capability
        By default sets the vertex to the origin (0, 0)
        :param x: float, x-axis coordinates
        :param y: float, y-axis coordinates
        :param edge: one edge starting from the vertex
        """
        self._x = truncate(x)
        self._y = truncate(y)
        self._edge = edge
        self.mutable = mutable
        super().__init__(mesh, _id)

    def __repr__(self):
        return 'vertex: ({x}, {y}) - {i}'.format(x=self.x, y=self.y, i=self.id)

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
        self._x = truncate(float(value))

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
        self._y = truncate(float(value))

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
    def coords(self) -> Coords2d:
        """
        Returns the coordinates of the vertex in the form of a tuple
        :return:
        """
        return self.x, self.y

    @coords.setter
    def coords(self, value: Coords2d):
        """
        Sets the vertex coordinates via a tuple
        :param value:
        :return:
        """
        self.x = value[0]
        self.y = value[1]

    @property
    def as_sp(self):
        """
        Returns a shapely Point data structure
        :return: shapely Point
        """
        return Point(self.x, self.y)

    @property
    def edges(self) -> Generator['Edge', 'Edge', None]:
        """
        Returns all edges starting from the vertex
        :return: generator
        """
        yield self.edge
        edge = self.edge.previous.pair
        while edge is not self.edge:
            yield edge
            edge = edge.previous.pair

    def clean(self) -> List['Edge']:
        """
        Removes an unneeded vertex.
        It is a vertex that is used only by two aligned edges, which could be replaced by
        one unique edge (and its pair edge of course).
        :return: the list of modified edges
        """
        # only clean a mutable vertex
        if not self.mutable:
            return []

        edges = list(self.edges)
        nb_edges = len(edges)
        # check the number of edges starting from the vertex
        if nb_edges > 2:
            logging.debug('Mesh: Cannot clean a vertex used by more than one edge')
            return []
        # only a vertex with two edges can be cleaned
        if nb_edges == 2:
            previous_edge = self.edge.previous
            if previous_edge.pair is not edges[1]:
                raise ValueError('Vertex is malformed' +
                                 ' and cannot be cleaned:{0}'.format(self))
            if previous_edge.next_is_aligned:
                edge = self.edge
                # preserve references
                edge.preserve_references()
                edge.pair.next.preserve_references()

                # removes both edges from the mesh
                edge.remove_from_mesh()
                edge.pair.next.remove_from_mesh()

                # adjust references
                previous_edge.next = edge.next
                edge.pair.next = edge.pair.next.next

                # create a new pair
                edge.pair.pair = previous_edge
                previous_edge.pair = edge.pair

                # remove the vertex
                self.remove_from_mesh()

                return [edge, edge.pair.next]

    def is_close(self, other: 'Vertex') -> bool:
        """
        Pseudo equality operator used for snapping
        :param other:
        :return:
        """
        return self.distance_to(other) <= COORD_EPSILON

    def project_point(self, face: 'Face',
                      vector: Vector2d) -> Optional[Tuple['Vertex', 'Edge', float]]:
        """
        Returns the projected point according to the vector direction
        on the face boundary according to the provided vector.
        Note: the vertex has to be inside the face.
        Note: this does not split the edge the point is projected unto
        :param face:
        :param vector:
        :return: a tuple containing the new vertex and the associated edge, and the distance from
        the projected vertex
        """
        # iterate trough every edge of the face
        closest_edge = None
        closest_point = None
        shortest_distance = math.inf
        for edge in face.edges:

            if dot_product(edge.normal, vector) >= 0:
                continue

            # do not project on edges that starts or end with the vertex
            if self in (edge.start, edge.end):
                continue

            projected_point = project_point_on_segment(self.coords, vector,
                                                       (edge.start.coords, edge.end.coords),
                                                       epsilon=COORD_EPSILON)
            if projected_point is None:
                continue

            distance_to_point = distance(projected_point, self.coords)
            if distance_to_point < shortest_distance:
                closest_edge = edge
                closest_point = projected_point
                shortest_distance = distance_to_point

        if not closest_point:
            return None

        new_vertex = Vertex(face.mesh, *closest_point)

        return (new_vertex, closest_edge, shortest_distance) if closest_edge else None

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
        Used to snap a vertex to another one that is close.
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
            if self.is_close(other):
                # ensure that the reference to the vertex are still valid
                if self.edge is not None:
                    for edge in list(self.edges):
                        edge.start = other
                    self.edge = None
                # remove the vertex from the mesh
                if self.mesh:
                    self.remove_from_mesh()
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
        best_edge = None
        min_angle = None
        vector = self.edge.vector if self.edge else None
        for edge in edges:
            new_edge = None
            # if the vertex has an edge we make sure that we snap to the correct edge pair.
            # this is needed only for internal edge
            # NOTE : very important, the vertex must move not the edge !
            if self is edge.start or self.snap_to(edge.start) is not self:
                new_edge = edge
            elif self is edge.end or self.snap_to(edge.end) is not self:
                new_edge = edge.next
            else:
                closest_point = project_point_on_segment(self.coords, edge.normal,
                                                         (edge.start.coords, edge.end.coords),
                                                         no_direction=True, epsilon=COORD_EPSILON)
                dist = distance(self.coords, closest_point) if closest_point else math.inf
                if dist <= COORD_EPSILON:
                    self.coords = closest_point
                    new_edge = edge.split(self)

            if new_edge is None:
                continue

            internal_edge = (edge.is_internal or edge.pair.next
                             or edge.pair.next.pair.next.is_internal)

            if not internal_edge or not self.edge:
                best_edge = new_edge
                break

            # check if we have a correct edge in case of an internal edge
            new_angle = ccw_angle(new_edge.vector, vector)
            # note : we must check that the edge is not just slightly on the clockwise side
            # of the new_edge
            if pseudo_equal(new_angle, 360.0, ANGLE_EPSILON):
                new_angle = 0.0
            if min_angle is None or min_angle > new_angle:
                best_edge = new_edge
                min_angle = new_angle
                if pseudo_equal(min_angle, 0.0, ANGLE_EPSILON):
                    break
        return best_edge

    def vector(self, other: 'Vertex') -> Vector2d:
        """
        Returns the vector between two vertices
        """
        return other.x - self.x, other.y - self.y

    def sp_half_line(self,
                     vector: Vector2d,
                     length: float = LINE_LENGTH) -> LineString:
        """
        Returns a shapely LineString starting
        from the vertex, slightly moved in the opposite vector and following the vector
        and of the given length

        Example :
        -Ɛ/2     Full line
        <- * ------------->
        vertex  length

        :param vector: direction of the lineString
        :param length: float length of the lineString
        :return: a LineString object
        """
        length = length or LINE_LENGTH
        vector = unit(vector)
        # to ensure proper intersection we shift slightly the start point
        start_point = move_point(self.coords, vector, -1 / 2 * COORD_EPSILON)
        end_point = move_point(start_point, vector, length)
        return LineString([start_point, end_point])


class Edge(MeshComponent):
    """
    Half Edge class
    """

    type = MeshComponentType.EDGE

    __slots__ = '_start', '_next', '_face', '_pair'

    def __init__(self, mesh: 'Mesh', start: Optional[Vertex] = None,
                 next_edge: Optional['Edge'] = None, pair: Optional['Edge'] = None,
                 face: Optional['Face'] = None, _id: Optional[int] = None):
        """
        A half edge data structure implementation.
        By convention our half edge structure is based on a CCW rotation.
        :param mesh: Mesh containing the edge
        :param start: Vertex starting point for the edge
        :param pair: twin edge of opposite face
        :param face: the face that the edge belongs to,
        can be set to None for external edges
        :param next_edge: the next edge
        """
        # initializing the data structure
        self._start = start
        self._next = next_edge
        self._face = face
        self._pair = pair
        # ensure that the pair edge is reciprocal
        if pair is not None:
            pair.pair = self
        # check the size of the edge (not really useful)
        super().__init__(mesh, _id)
        self.check_size()

    def __repr__(self):
        output = 'Edge:[({x1}, {y1}), ({x2}, {y2})] - {i}'.format(x1=self.start.x,
                                                                  y1=self.start.y,
                                                                  x2=self.end.x,
                                                                  y2=self.end.y,
                                                                  i=self.id)
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
        # TODO: is this necessary ?
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
    def is_mesh_boundary(self):
        """
        Returns True if the edge is one the boundary of the mesh
        :return:
        """
        return self.pair.face is None or self.face is None

    @property
    def is_internal(self):
        """
        Returns True if the edge is inside the face (in the case of a face with a hole)
        :return:
        """
        return self.pair.face is self.face

    @property
    def cardinality(self) -> int:
        """
        Counts the number of edges linked to the start or end of the edge
        Example : this edge has a cardinality of 5
             +               +
             |     EDGE      |
        +----*---------------*
             |               |
             +               +
        :return:
        """
        number_edges_start = len(list(self.start.edges)) - 1
        number_edges_end = len(list(self.end.edges)) - 1
        return number_edges_end + number_edges_start

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
        is_aligned = pseudo_equal(self.next_angle, 180, ANGLE_EPSILON)
        return is_aligned

    @property
    def previous_is_aligned(self) -> bool:
        """
        Indicates if the next edge is approximately aligned with this one,
        using a pseudo equality on the angle
        :return: boolean
        """
        is_aligned = pseudo_equal(self.previous_angle, 180, ANGLE_EPSILON)
        return is_aligned

    @property
    def next_is_ortho(self) -> bool:
        """
        Indicates if the next edge is orthogonal
        :return:
        """
        return pseudo_equal(self.next_angle, 90, ANGLE_EPSILON)

    def next_ortho(self) -> 'Edge':
        """
        Returns the next orthogonal edge
        :return:
        """
        angle = 0
        for edge in self.siblings:
            angle += ccw_angle(edge.vector, edge.next.vector)
            if angle >= 90.0 - ANGLE_EPSILON:
                return edge.next

        raise Exception('The impossible has happened !!')

    def previous_ortho(self) -> 'Edge':
        """
        Returns the previous orthogonal edge
        :return:
        """
        angle = 0
        for edge in self.reverse_siblings:
            angle += ccw_angle(edge.previous.vector, edge.vector)
            if angle >= 90.0 - ANGLE_EPSILON:
                return edge.previous

        raise Exception('The impossible has happened !!')

    @property
    def previous_is_ortho(self) -> bool:
        """
        Indicates if the next edge i
        :return:
        """
        return pseudo_equal(self.previous_angle, 90, ANGLE_EPSILON)

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
        return unit(self.vector)

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
        # per convention if the edge is of length 0 we return the 0, 0 vector
        if self.length == 0:
            return 0, 0

        x, y = -self.vector[1], self.vector[0]
        length = math.sqrt(x ** 2 + y ** 2)
        return x / length, y / length

    @property
    def depth(self) -> float:
        """
        Returns the depth of the face along the normal of the edge from the middle of the face
        :return:
        Example :
            *<----+------*
            |     ^      ^
            |     |Depth |
            |     |      |
            v     |      |
            *-----+----->*
                Edge
        """
        if not self.face:
            return 0.0

        middle_point = barycenter(self.start.coords, self.end.coords, 0.5)
        vector = self.normal
        min_depth = math.inf

        for edge in self.siblings:
            if edge is self:
                continue
            point = project_point_on_segment(middle_point, vector,
                                             (edge.start.coords, edge.end.coords))
            if not point:
                continue
            distance_to_point = distance(point, middle_point)
            if distance_to_point < min_depth:
                min_depth = distance_to_point

        return min_depth

    def max_distance(self, other: 'Edge', parallel: bool = False) -> float:
        """
        Returns the max distance between to edges of the same face, according to the normal
        vector of the edge. If the distance is infinite return INFINITY per convention.
        :param other:
        :param parallel: flag to indicate whether we only consider pseudo parallel edges
        :return: the distance

        Example:
          ^
          |             OTHER
          |        <-------+-------*
          |        |       ^       |
          |        |       |       |
         d1       d4      d2      d3
          |        |       |       |
          |        |       |       |
          +--------v------->       |
               SELF                |
                                   v
        """

        if self.face is None or self.face is not other.face:
            raise ValueError("Cannot compute the distance of two edges not in the same face")

        # ATTENTION : if the edge is not quasi parallel to the edge return infinity
        if parallel and not pseudo_equal(ccw_angle(other.vector, self.vector), 180.0, 15.0):
            return INFINITY

        normal = self.normal
        opposite_normal = opposite_vector(normal)
        self_start, self_end = self.start.coords, self.end.coords
        other_start, other_end = other.start.coords, other.end.coords

        p1 = project_point_on_segment(self_start, normal, (other_start, other_end))
        d1 = distance(self_start, p1) if p1 is not None else None

        p2 = project_point_on_segment(self_end, normal, (other_start, other_end))
        d2 = distance(self_end, p2) if p2 is not None else None

        p3 = project_point_on_segment(other_start, opposite_normal, (self_start, self_end))
        d3 = distance(other_start, p3) if p3 is not None else None

        p4 = project_point_on_segment(other_end, opposite_normal, (self_start, self_end))
        d4 = distance(other_end, p4) if p4 is not None else None

        dist_max_to_edge = max((d for d in (d1, d2, d3, d4) if d is not None), default=INFINITY)
        return dist_max_to_edge

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
        start_point = move_point(self.start.coords, vector, -1 * COORD_EPSILON)
        return LineString([start_point, end_point])

    @property
    def as_sp_dilated(self) -> Polygon:
        """
        Returns a dilated lineString to ensure snapping
        in order to prevent near miss due to floating point precision
        :return: a shapely Polygon
        """
        return self.as_sp.buffer(COORD_EPSILON, 1)

    # noinspection PyUnreachableCode
    @property
    def siblings(self) -> Generator['Edge', None, None]:
        """
        Returns the siblings of the edge, starting with itself.
        :return: generator yielding each edge in the loop
        """
        yield self
        edge = self.next
        # in order to detect infinite loop we stored each yielded edge
        if __debug__:
            seen = []
        while edge is not self:
            if __debug__ and edge in seen:
                raise Exception('Infinite loop' +
                                ' starting from edge:{0}'.format(self))
            if __debug__:
                seen.append(edge)
            yield edge
            edge = edge.next

    # noinspection PyUnreachableCode
    @property
    def reverse_siblings(self) -> Generator['Edge', 'Edge', None]:
        """
        Returns the siblings of the edge, starting with itself
        looping in reverse
        :return: generator yielding each edge in the loop
        """
        yield self
        edge = self.previous
        # in order to detect infinite loop we stored each yielded edge
        if __debug__:
            seen = []
        while edge is not self:
            if __debug__:
                if edge in seen:
                    raise Exception('Infinite loop' +
                                    ' starting from edge:{0}'.format(self))
                seen.append(edge)
            yield edge
            edge = edge.previous

    @property
    def aligned_siblings(self) -> Generator['Edge', 'Edge', None]:
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

    @property
    def line(self) -> ['Edge']:
        """
        Returns all the edges that form a straight line with the current edge
        :return: a list of contiguous edges
        """
        output = []

        # going forward
        current = self
        while current:
            output.append(current)
            current = current.aligned_edge or current.continuous_edge

        # going backward
        current = self.pair.aligned_edge or self.pair.continuous_edge
        while current:
            output = [current.pair] + output
            current = current.aligned_edge or current.continuous_edge

        return output

    @property
    def aligned_edge(self) -> Optional['Edge']:
        """
        Returns the edge aligned with the edge
        :return: an aligned edge or None
        Example:
                   |
           self    | aligned_edge
        +--------->*---------->
                   |
                   |
                   v
        """
        if self.next_is_aligned:
            return self.next
        for _edge in self.end.edges:
            if _edge.pair is self:
                continue
            if pseudo_equal(ccw_angle(self.vector, _edge.opposite_vector), 180, ANGLE_EPSILON):
                return _edge

        return None

    @property
    def continuous_edge(self) -> Optional['Edge']:
        """
        Returns the edge in the continuity of the edge, when crossing another line.
        Note : the end vertex of the edge must have exactly 4 outgoing edges, two of them must
        be aligned.
                   +
                   |
                   | EDGE
                   |
                   v
        +--------->*--------->
                   .|
                   . |  CONTINUOUS EDGE
                   .  |
                   .   |
                   .    v
        :return:
        """
        edges = [self.pair]
        current = self.next
        while current is not self.pair:
            edges.append(current)
            current = current.pair.next

        if len(edges) != 4:
            return None

        if not pseudo_equal(ccw_angle(edges[1].vector, edges[3].vector),
                            180.0, ANGLE_EPSILON):
            return None

        return edges[2]

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

    def contains(self, vertex: Vertex) -> bool:
        """
        Returns True if the edge contains the vertex
        :return: bool
        """
        return self.as_sp_dilated.intersects(vertex.as_sp)

    def barycenter(self, coeff: float) -> Vertex:
        """
        Returns True if the edge contains the vertex
        :return: vertex
        """
        vertex = (transformation.get['barycenter']
                  .config(vertex=self.end, coeff=coeff)
                  .apply_to(self.start))
        return vertex

    def collapse(self):
        """
        Collapse an edge by merging start and end vertices
        :return:
        """
        # snap vertices
        self.start = self.start.snap_to(self.end)
        # preserve references
        self.preserve_references()
        self.pair.preserve_references()
        # insure next pointers for edge and pair edge
        self.previous.next = self.next
        self.pair.previous.next = self.pair.next

        # remove the edge from the mesh
        self.remove_from_mesh()
        self.pair.remove_from_mesh()

    def remove(self, clean_vertex: bool = True) -> 'Face':
        """
        Removes the edge from the face. The corresponding faces are merged
        1. remove the face of the edge from the mesh (except if the face is None, in which case
        we remove the face of the edge pair)
        2. stitch the extremities of the removed edge
        3. attribute correct face to orphan edges
        :return: the remaining face after the edge was removed
        """
        # attribute new face to orphan
        # note if the edge is a boundary edge we attribute the edge face
        # to the pair edge siblings, not the other way around
        other_face = self.pair.face
        removed_face = self.face if self.face is not None else other_face
        remaining_face = other_face if self.face is not None else None

        if self.face is None or self.pair.face is None:
            logging.warning("Edge: Removing and edge on the boundary of the plan")

        # Check if the *self* edge is an internal edge of the face
        # we can only remove it if it's also an isolated edge, meaning it should end on a lone
        # vertex
        if self.is_internal:
            # we cannot remove an edge that is needed to connect a face hole to the face
            # boundary, so we have to check that the edge ends in a lone vertex
            if self.next is not self.pair and self.pair.next is not self:
                raise ValueError('cannot remove an edge that will create an' +
                                 ' unconnected hole in a face: {0}'.format(self))

            logging.debug('Mesh: Removing an isolated edge: {0}'.format(self))
            isolated_edge = self if self.next is self.pair else self.pair
            # remove end vertex from mesh
            isolated_edge.preserve_references(isolated_edge.pair.next)
            isolated_edge.pair.preserve_references(isolated_edge.pair.next)
            isolated_edge.previous.next = isolated_edge.pair.next
            isolated_edge.end.remove_from_mesh()
            isolated_edge.start.clean()
        else:
            # preserve references
            self.preserve_references()
            self.pair.preserve_references()

            # change face references
            for edge in removed_face.edges:
                edge.face = remaining_face

            removed_face.remove_from_mesh()

            # stitch the edge extremities
            self.pair.previous.next = self.next
            self.previous.next = self.pair.next

            # clean potentially useless vertices
            if clean_vertex:
                self.start.clean()
                self.end.clean()

        # Finish :
        # remove the edge and its pair, and the removed face from the mesh
        self.remove_from_mesh()
        self.pair.remove_from_mesh()

        # remove the potentially remaining isolated edges in the face
        for edge in remaining_face.edges:
            if edge.next is edge.pair:
                edge.remove()
                break

        return remaining_face

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

    def intersect(self,
                  vector: Vector2d,
                  max_length: Optional[float] = None) -> Optional['Edge']:
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
            # clean unused vertex
            intersection_vertex.remove_from_mesh()
            return None

        # split the destination edge
        closest_edge = closest_edge.split(intersection_vertex)

        # if the destination edge cannot be split return None
        if closest_edge is None:
            # clean unused vertex
            intersection_vertex.remove_from_mesh()
            return None

        return closest_edge.previous

    def link(self, other: 'Edge') -> Optional['Face']:
        """
        Per convention we link the end of the edges and not the start.
        TODO : Might no be the best convention.

        Creates an edge between two edges.
        We link the end vertices of each edge
        Note : we cannot linked two edges that are already linked
        (meaning that they are the next edge of each other)
        :param other: the edge to link to
        :return: the created face, the initial face if modified, None if the mesh was not modified
        """
        # check if the edges have the same face
        if self.face is not other.face:
            raise ValueError('Cannot link two edges that do not share the same face: ' +
                             '{0}-{1}'.format(self, other))

        # check if the edges are already linked
        if other.next is self or self.next is other:
            # APP-7308: Second pass for warnings
            logging.info('Mesh: Cannot link two edges that are already linked:%s-%s', self, other)
            return None

        # check if the edges are the same
        if self.end is other.end:
            logging.warning('cannot link one vertex to itself ' +
                            ':{0}-{1}'.format(self, other))
            return None

        # Create the new edge and its pair
        new_edge = Edge(self.mesh, self.end, other.next, face=self.face)
        self.face.edge = self  # preserve split face edge reference
        new_edge.pair = Edge(self.mesh, other.end, self.next, pair=new_edge)

        # modify initial edges next edges to follow the laser_cut
        self.next = new_edge
        other.next = new_edge.pair

        # create a new face
        new_face = Face(self.mesh, new_edge.pair)

        # assign all the edges from one side of the laser_cut to the new face
        for edge in new_edge.pair.siblings:
            edge.face = new_face

        # store the specific mesh operation
        self.mesh.store_modification(MeshOps.INSERT, new_face, self.face)

        return new_face

    def recursive_cut(self,
                      vertex: Vertex,
                      angle: float = 90.0,
                      traverse: str = 'absolute',
                      vector: Optional[Vector2d] = None,
                      max_length: Optional[float] = None,
                      callback: Optional[SpaceCutCb] = None) -> TwoEdgesAndAFace:
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
        new_edges_and_face = self.cut(vertex, angle, vector=vector, max_length=max_length)

        # if the cut fail we stop
        if new_edges_and_face is None:
            return None

        # do not continue to cut if not needed
        if traverse not in ("absolute", "relative"):
            if callback:
                callback(new_edges_and_face)
            return new_edges_and_face

        new_edge_start, new_edge_end, new_face = new_edges_and_face

        # check if we have the correct new_edge_end
        # a correct edge should enable a next cut
        correct_edge: 'Edge' = new_edge_end
        next_angle = ccw_angle(correct_edge.pair.vector, vector)
        while (not correct_edge.pair._angle_inside_face(next_angle)
               and correct_edge is not new_edge_end):
            correct_edge = correct_edge.cw
            next_angle = ccw_angle(correct_edge.pair.vector, vector)
        new_edge_end = correct_edge

        new_edges_and_face = new_edge_start, new_edge_end, new_face

        # call the callback to check if the cut should stop
        if callback and callback(new_edges_and_face):
            return new_edges_and_face

        # check the distance
        if max_length is not None and new_edge_start is not None:
            distance_traveled = new_edge_start.start.distance_to(new_edge_end.start)
            max_length -= distance_traveled

        # laser_cut the next edge if traverse option is set
        # if the new cut is unfruitful we do not return None but the last cut data
        vector = vector if traverse == 'absolute' else None
        new_edges_and_face = (new_edge_end.pair.recursive_cut(new_edge_end.start, angle,
                                                              traverse=traverse,
                                                              vector=vector,
                                                              max_length=max_length,
                                                              callback=callback)
                              or new_edges_and_face)
        return new_edges_and_face

    def _angle_inside_face(self, angle: float) -> bool:
        """
        Returns True if the angle is inside the face of the edge.
        Consider the direction starting from the end vertex of the edge.
        :return:
        """
        angle_is_inside = 180 - MIN_ANGLE > angle > 180.0 - self.next_angle + MIN_ANGLE
        if not angle_is_inside:
            logging.debug('Mesh: Cannot cut according to angle:{0} > {1} > {2}'.
                          format(180 - MIN_ANGLE, angle, 180.0 - self.next_angle + MIN_ANGLE))
            return False
        return True

    def cut(self,
            vertex: Vertex,
            angle: float = 90.0,
            vector: Optional[Vector2d] = None,
            max_length: Optional[float] = None) -> TwoEdgesAndAFace:
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
        if vertex is self.start:
            first_edge = self.previous
            angle = angle + 180.0 - self.previous_angle

        if vertex is first_edge.end and not first_edge._angle_inside_face(angle):
            return None

        # split the starting edge
        first_edge.split(vertex)

        # create a line to the edge at the vertex position
        line_vector = vector or unit_vector(ccw_angle(self.vector) + angle)
        closest_edge = first_edge.intersect(line_vector, max_length)

        # if no intersection can be found return None
        if closest_edge is None:
            # APP-7308: Second pass for warnings
            logging.info('Mesh: Could not create a viable cut')
            return None

        # assign a correct edge to the initial face
        # (to ensure that its edge is still included in the face)
        first_edge.face.edge = first_edge

        # per convention we return the two edges starting
        # from the cut vertex and the intersection vertex
        closest_edge_next = closest_edge.next
        first_edge_next = first_edge.next

        # link the two edges
        new_face = first_edge.link(closest_edge)
        # check to see if the link was properly executed.
        # if not, it means that the closest edge was linked to the first edge
        # to prevent recursion while laser cutting if the first_edge is the closest_edge next edge
        # we return a different edge as the next edge to cut

        if new_face is None:
            if closest_edge.next is first_edge:
                closest_edge_next = first_edge.pair.next

        return first_edge_next, closest_edge_next, new_face

    def recursive_barycenter_cut(self, coeff: float,
                                 angle: float = 90.0,
                                 vector: Optional[Vector2d] = None,
                                 traverse: str = 'relative') -> TwoEdgesAndAFace:
        """
        Laser cuts an edge according to the provided angle (90° by default)
        and at the barycentric position
        :param coeff:
        :param angle:
        :param vector:
        :param traverse: type of recursion
        :return:
        """
        if coeff == 0:
            vertex = self.start
        elif coeff == 1:
            vertex = self.end
        else:
            vertex = (transformation.get['barycenter']
                      .config(vertex=self.end, coeff=coeff)
                      .apply_to(self.start))

        cut_data = self.recursive_cut(vertex, angle, vector=vector, traverse=traverse)

        # clean vertex if the cut fails
        if cut_data is None and vertex.edge is None:
            vertex.remove_from_mesh()

        return cut_data

    def barycenter_cut(self,
                       coeff: float = 0.5,
                       angle: float = 90.0,
                       vector: Optional[Vector2d] = None) -> TwoEdgesAndAFace:
        """
        Cuts an edge according to the provided angle (90° by default)
        and at the barycentric position
        :param coeff:
        :param angle:
        :param vector:
        :return:
        """
        if coeff == 0:
            vertex = self.start
        elif coeff == 1:
            vertex = self.end
        else:
            vertex = (transformation.get['barycenter']
                      .config(vertex=self.end, coeff=coeff)
                      .apply_to(self.start))

        cut_data = self.cut(vertex, angle, vector=vector)

        # clean vertex if the cut fails
        if cut_data is None and vertex.edge is None:
            vertex.remove_from_mesh()

        return cut_data

    def ortho_cut(self) -> TwoEdgesAndAFace:
        """
        Tries to cut the edge face at the edge start vertex in an orthogonal projection to any
        edge of the face
        :return: the new created faces
        """
        projected_vertex = None

        for edge in self.siblings:
            # we do not check the two edges touching the vertex
            if edge is self or edge is self.previous:
                continue

            vector = opposite_vector(edge.normal)
            # check if we are cutting trough the edge
            angle = ccw_angle(self.vector, vector)
            angle_is_inside = MIN_ANGLE < angle < self.previous_angle - MIN_ANGLE
            if not angle_is_inside:
                logging.debug('Mesh: Cannot cut according to angle:{0} < {1} < {2}'.
                              format(MIN_ANGLE, angle, self.previous_angle - MIN_ANGLE))
                continue

            projected_vertex = (transformation.get['projection']
                                .config(vector=vector, edge=edge)
                                .apply_to(self.start))
            # If we can not project orthogonally on the edge we continue
            if projected_vertex is None:
                continue

            # Check if we cross the boundary of the face
            min_distance = projected_vertex.distance_to(self.start)
            closest_edge = edge

            for other_edge in edge.siblings:
                # we do not check the two edges touching the vertex
                if other_edge is self or other_edge is self.previous:
                    continue

                other_projected_vertex = (transformation.get['projection']
                                          .config(vector=vector, edge=other_edge)
                                          .apply_to(self.start))

                if other_projected_vertex is None:
                    continue

                other_distance = other_projected_vertex.distance_to(self.start)

                if other_distance < min_distance:
                    # clean unused vertex
                    if projected_vertex:
                        projected_vertex.remove_from_mesh()

                    projected_vertex = other_projected_vertex
                    min_distance = other_distance
                    closest_edge = other_edge

                else:
                    # clean unused vertex
                    other_projected_vertex.remove_from_mesh()

            split_edge = closest_edge.split(projected_vertex)

            # check if we the split was successful
            if split_edge is None:
                projected_vertex.remove_from_mesh()
                continue

            split_edge_previous = split_edge.previous
            self_previous = self.previous

            new_face = self_previous.link(split_edge_previous)

            if new_face is None:
                if projected_vertex.mesh:
                    projected_vertex.remove_from_mesh()
                continue

            return self, split_edge, new_face

        # clean unused vertex
        if projected_vertex and not projected_vertex.edge:
            projected_vertex.remove_from_mesh()

        return None

    def split(self, vertex: 'Vertex') -> Optional['Edge']:
        """
        Splits the edge at a specific vertex.
        We create two new half-edges:

        ---------> - - - ->
        old edge  • new edge
        <- - - - - <-------
        new pair   old pair

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

        # define edges names for clarity sake
        edge = self
        next_edge = self.next
        edge_pair = self.pair
        next_edge_pair = self.pair.next

        # create the two new half edges
        new_edge = Edge(self.mesh, vertex, next_edge, edge_pair, edge.face)
        new_edge_pair = Edge(self.mesh, vertex, next_edge_pair, edge, edge_pair.face)

        vertex.edge = vertex.edge if vertex.edge is not None else new_edge

        # change the current edge destinations and starting point
        new_edge_pair.next = next_edge_pair
        new_edge.next = next_edge
        edge.next = new_edge
        edge_pair.next = new_edge_pair

        # store modification
        self.mesh.store_modification(MeshOps.INSERT, new_edge, self)
        self.mesh.store_modification(MeshOps.INSERT, new_edge_pair, self.pair)

        return new_edge

    def slice(self, offset: float, vector: Optional[Vector2d] = None) -> ['Face']:
        """
        Cuts the face of the edge according to the offset and the vector provided.
        Note: Can result in the creation of multiple faces.

        Example:
            +-------------------------+
            |                         |
            |       New face          |
            |                         |
            |       Line cut          | vector ->
        +---*-----------+-------------*---+
            |           ^             |
            |           | offset      |
            |           |             |
            |           |             |
            +-----------+-------------+
            +---------+EDGE+---------->

        :param offset: the distance along the edge normal
        :param vector: the direction of the created edge
        :return: a list of the created faces including the initial face
        """
        logging.debug("Edge: Slicing a face from edge %s with offset %s and vector %s",
                      self, offset, vector)

        if offset < 0:
            raise ValueError("Edge: Slice: The offset must be a positive float")

        if self.face is None:
            raise ValueError("Edge Slice: The edge must fave a non null face")

        # per convention we slice parallel to the edge direction
        vector = vector or opposite_vector(self.vector)

        point = move_point(self.start.coords, self.normal, offset)
        vertex = Vertex(self.mesh, point[0], point[1])
        created_faces = self.face.slice(vertex, vector)
        vertex.remove_from_mesh()

        return created_faces

    def split_barycenter(self, coeff: float) -> 'Edge':
        """
        Splits the edge at the provided barycentric position. A vertex is created.
        :param coeff: float
        :return: self
        """
        vertex = (transformation.get['barycenter']
                  .config(vertex=self.end, coeff=coeff)
                  .apply_to(self.start))
        return self.split(vertex)

    def plot(self, ax, color: str = 'black', save: Optional[bool] = None,
             width: Optional[float] = 1.0):
        """
        Plots the edge
        :param ax:
        :param color:
        :param save:
        :return:
        """
        x_coords, y_coords = zip(*(self.start.coords, self.end.coords))
        return plot_edge(x_coords, y_coords, ax, color=color, save=save, width=width)

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
            raise ValueError('Cannot create and edge starting and ending with the same ' +
                             'vertex: {0}'.format(self.start))

        if self.start and self.end and self.length < COORD_EPSILON / 4:
            logging.info('Mesh: Created a very small edge: {0} - {1}'.format(self.start, self.end))


class Face(MeshComponent):
    """
    Face Class
    """

    type = MeshComponentType.FACE

    __slots__ = '_edge', '_cached_area'

    def __init__(self, mesh: 'Mesh', edge: 'Edge', _id: Optional[int] = None):

        self._edge = edge
        super().__init__(mesh, _id)

        # for performance purposes
        self._cached_area = None

    def __repr__(self):
        output = 'Face: ['
        for edge in self.edges:
            output += '({0}, {1})'.format(*edge.start.coords)
        return output + '] - {}'.format(self.id)

    def swap(self, face: Optional['Face'] = None):
        """
        Creates a copy of the face and attributes it to the self edges
        :return:
        """
        if face is None:
            new_face = Face(self.mesh, self.edge)
        else:
            new_face = face
            new_face.edge = self.edge
            new_face.add_to_mesh(self.mesh, new_face.id)

        # swap edge references
        for edge in self.edges:
            edge.face = new_face

        # preserve vertices references
        for vertex in new_face.vertices:
            for edge in self.edges:
                if edge.start is vertex:
                    vertex.edge = edge

        self.remove_from_mesh()
        return new_face

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
        return edge.siblings

    @property
    def vertices(self) -> Generator[Vertex, None, None]:
        """
        Lists the vertices on the edges of the face
        :return: Generator
        """
        return (edge.start for edge in self.edges)

    @property
    def coords(self):
        """
        Returns the list of the coordinates of the face
        :return:
        """
        return [vertex.coords for vertex in self.vertices]

    @property
    def as_sp(self) -> Polygon:
        """
        Returns a shapely Polygon corresponding to the face geometry
        :return: Polygon
        """
        list_vertices = [vertex.coords for vertex in self.vertices]
        list_vertices.append(list_vertices[0])
        return Polygon(list_vertices)

    @property
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
    def as_sp_eroded(self) -> Polygon:
        """
        Returns a dilated Polygon corresponding to the face with a small buffer
        This is useful to prevent floating point precision errors.
        :return: Polygon
        """
        return self.as_sp.buffer(-COORD_EPSILON, 1)

    @property
    def area(self) -> float:
        """
        Calculates and returns the area of the face
        We use the shapely module to compute the area
        :return: float
        """
        return self.as_sp.area

    @property
    def cached_area(self) -> float:
        """
        property
        Returns the cached area of the face
        :return:
        """
        if self._cached_area is None:
            self._cached_area = self.area
        return self._cached_area

    @cached_area.setter
    def cached_area(self, value: float):
        """
        Computes the cache
        :param value:
        :return:
        """
        self._cached_area = value

    @property
    def length(self) -> float:
        """
        Calculates the perimeter length of the face
        We use the shapely module to compute the perimeter
        :return: float
        """
        return self.as_sp.length

    @property
    def perimeter(self) -> float:
        """
        Calculate the perimeter length of the face (not using shapely)
        :return:
        """
        return sum(map(lambda e: e.length, self.edges))

    def distance_to(self, other: 'Face', kind: str = "max") -> float:
        """
        Returns the max or the min distance to the other face
        :param other:
        :param kind: whether to return the max or the min distance
        :return:
        """
        choices = {
            "min": min,
            "max": max
        }

        return choices[kind]((v1.distance_to(v2)
                              for v1 in self.vertices for v2 in other.vertices))

    @property
    def internal_edges(self) -> Generator[Edge, None, None]:
        """
        Returns the internal edges of the face.
        An internal edge is defined has having the same face as its pair
        :return:
        """
        return (edge for edge in self.edges if edge.pair.face is self)

    @property
    def has_internal_edge(self) -> bool:
        """
        Returns True if the face has at least one internal edge.
        :return:
        """
        try:
            next(iter(self.internal_edges))
            return True
        except StopIteration:
            return False

    def siblings(self,
                 min_adjacency_length: Optional[float] = None) -> Generator['Face', 'Edge', None]:
        """
        Returns all adjacent faces and itself
        :param min_adjacency_length:
        :return:
        """
        seen = [self]
        yield self

        if min_adjacency_length is not None:
            for edge in self.edges:
                if (edge.pair.face is not None and edge.pair.face not in seen
                        and edge.length >= min_adjacency_length):
                    seen.append(edge.pair.face)
                    yield edge.pair.face
        else:
            for edge in self.edges:
                if edge.pair.face is not None and edge.pair.face not in seen:
                    seen.append(edge.pair.face)
                    yield edge.pair.face

    def is_adjacent(self, other: 'Face') -> bool:
        """
        Returns True if the face *self* is adjacent to the face *other*
        :param other:
        :return:
        """
        for edge in self.edges:
            if edge.pair.face is other:
                return True
        return False

    def bounding_box(self, vector: Vector2d = None) -> Tuple[float, float]:
        """
        Returns the bounding rectangular box of the face according to the direction vector
        :param vector:
        :return: the width and depth of the box
        """
        vector = unit(vector) if vector is not None else self.edge.unit_vector
        total_x = 0
        max_x = 0
        min_x = 0
        total_y = 0
        max_y = 0
        min_y = 0
        number_of_turns = 0

        for other in self.edges:
            total_x += dot_product(other.vector, vector)
            max_x = max(total_x, max_x)
            min_x = min(total_x, min_x)
            total_y += dot_product(other.vector, normal_vector(vector))
            max_y = max(total_y, max_y)
            min_y = min(total_y, min_y)
        number_of_turns += 1

        return max_x - min_x, max_y - min_y

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

    def crosses(self, other: 'Face') -> bool:
        """
        Returns true if the face are overlapping but the other face is not contained inside the face
        :param other:
        :return:
        """
        return self.as_sp_dilated.crosses(other.as_sp)

    def is_insertable(self, other: 'Face') -> bool:
        """
        Returns True if the other face can be inserted in the face
        :param other:
        :return:
        """
        if other.mesh is not self.mesh:
            raise ValueError("Cannot insert a face in another face from a different mesh")

        if not self.contains(other):
            if self.crosses(other):
                raise ValueError("Cannot insert a face that is" +
                                 " crossing the receiving face !:{0}".format(other))
            else:
                logging.info('Mesh: Other face is outside receiving face: %s -> %s', other, self)
                raise OutsideFaceError()
        return True

    def add_exterior(self, other: 'Face') -> 'Face':
        """
        Assigns to the external edge the provided face.
        Useful before inserting a face inside another
        :param other: face
        :return: self
        """
        for edge in self.edges:
            edge.pair.face = other

        return self

    def slice(self,
              vertex: Vertex,
              vector: Vector2d) -> List['Face']:
        """
        Cuts a face according to a linestring crossing the vertex and along the vector
        TODO : if the linestring is very close to an edge of the face, the result of the slice
               can be just the creation of a single vertex
        We must first create a point outside the face, in order to find every intersection point in
        the face. Then we link every point.
        :param vertex:
        :param vector:
        :return:
        """
        translation_vector = unit(vector)
        # We move the point far from the mesh to ensure that we are outside the face
        # note this is a fast way but not guaranteed if we have a very large face (larger or close
        # to the LINE_LENGTH
        reference_point = move_point(vertex.coords, translation_vector, -LINE_LENGTH)
        intersected_edges = set()
        for edge in self.edges:
            if dot_product(edge.normal, vector) <= 0:
                continue
            intersection_point = project_point_on_segment(reference_point, vector,
                                                          (edge.start.coords, edge.end.coords),
                                                          no_direction=True,
                                                          epsilon=COORD_EPSILON)
            if intersection_point:
                # we try to snap the vertex to the edge extremities
                intersected_edge = Vertex(self.mesh, *intersection_point).snap_to_edge(edge)
                intersected_edges.add(intersected_edge)

        if not intersected_edges:
            return [self]
        intersected_edges = list(intersected_edges)
        # sort the points via their distance to the reference point
        intersected_edges.sort(key=lambda e: distance(reference_point, e.start.coords))

        modified_faces = [self]

        for intersected_edge in intersected_edges:
            new_mesh_objects = intersected_edge.cut(intersected_edge.start, vector=vector)
            if new_mesh_objects:
                start_edge, end_edge, new_face = new_mesh_objects
                if new_face and new_face not in modified_faces:
                    modified_faces.append(new_face)

        return modified_faces

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
        vectors = [unit_vector(main_direction[0]) for main_direction in main_directions]

        # find the closest vertex of the face to the boundary of the receiving face
        # according to the mesh two main directions
        min_distance = None
        best_vertex = None
        best_near_vertex = None
        best_shared_edge = None
        for edge in face.edges:
            for vector in vectors:
                for vertex in (edge.pair.start, edge.pair.end):
                    angle = ccw_angle(edge.pair.normal, vector)
                    if angle <= 90.0 - MIN_ANGLE or angle >= 270.0 + MIN_ANGLE:
                        _vector = vector
                    elif 90 + MIN_ANGLE <= angle <= 270.0 - MIN_ANGLE:
                        _vector = opposite_vector(vector)
                    else:
                        continue
                    intersection_data = vertex.project_point(self, _vector)
                    if intersection_data is None:
                        continue
                    near_vertex, shared_edge, distance_to_vertex = intersection_data
                    projected_angle = ccw_angle(shared_edge.vector, vertex.vector(near_vertex)) % 90
                    if (not pseudo_equal(projected_angle, 0.0, ANGLE_EPSILON)
                            and not pseudo_equal(projected_angle, 90.0, ANGLE_EPSILON)):
                        # do not forget to clean unused vertex
                        near_vertex.remove_from_mesh()
                        continue
                    if min_distance is None or distance_to_vertex < min_distance:
                        best_vertex = vertex
                        # do not forget to clean unused vertex
                        if best_near_vertex:
                            best_near_vertex.remove_from_mesh()
                        best_near_vertex = near_vertex
                        best_shared_edge = shared_edge
                        min_distance = distance_to_vertex
                    else:
                        near_vertex.remove_from_mesh()

        if min_distance is None:
            raise Exception('Cannot find and intersection point to insert face !:{0}'.format(face))

        # create a new edge linking the vertex of the face to the enclosing face
        edge_shared = best_near_vertex.snap_to_edge(best_shared_edge)
        best_near_vertex = edge_shared.start  # ensure existing vertex reference
        new_edge = Edge(self.mesh, best_near_vertex, best_vertex.edge.previous.pair, face=self)
        new_edge.pair = Edge(self.mesh, best_vertex, edge_shared, new_edge, self)
        best_near_vertex.edge = new_edge
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
        (for example if other faces need to be inserted) the list of the created face is returned
        including the receiving face).

        ex: new_container_face = container_face.insert(face_to_insert)

        :param shared_edges:
        :return: the faces created or modified : the receiving face and the smaller face created
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
            # we preserve id for eventual references
            if previous_edge.pair.next.next is previous_edge.pair:
                # preserve references for face and vertex
                previous_edge.pair.preserve_references(previous_edge.pair.next.pair)
                previous_edge.pair.next.preserve_references(previous_edge)
                previous_touching_edge.preserve_references(previous_edge)
                # remove the edge from the mesh
                previous_edge.pair.remove_from_mesh()
                # remove the duplicate edges
                previous_edge.pair = previous_edge.pair.next.pair
                # swap the id to preserve references
                previous_edge.swap_id(previous_touching_edge)
                # remove the edge from the mesh
                previous_touching_edge.remove_from_mesh()

            # else check for new face creation
            elif not previous_edge.pair.is_linked_to_face(self):
                new_face = Face(self.mesh, previous_edge.pair)
                all_faces.append(new_face)
                for orphan_edge in previous_edge.pair.siblings:
                    orphan_edge.face = new_face

        # forward check : at the end of the loop check forward for isolation
        if edge.pair.next.next is edge.pair:
            # remove from the mesh
            touching_edge.preserve_references(edge)
            edge.pair.remove_from_mesh()
            edge.pair = touching_edge.pair
            # swap the id to preserve references
            edge.swap_id(touching_edge)
            # remove the edge from the mesh
            touching_edge.remove_from_mesh()
            # remove face from edge
            self.remove_from_mesh()  # Note : this is problematic for face absolute reference
            all_faces.pop(0)  # remove self from the list of all the faces

        # return the biggest face first per convention
        sorted_faces = sorted(all_faces, key=attrgetter('area'), reverse=True)

        return sorted_faces

    def _insert_identical_face(self, face: 'Face') -> List['Face']:
        """
        insert a identical face
        :param face:
        :return:
        """
        logging.debug('Mesh: The inserted face is equal to the container face : %s', face)
        # we swap self with the new inserted face
        # we remove the edges and vertices of the face from the mesh
        self.mesh.remove_face_and_children(face)
        # we need to add back the removed vertices
        for vertex in face.vertices:
            vertex.add_to_mesh(self.mesh)
        # we add again the face to the mesh
        self.swap(face)
        return []

    def _insert_face(self, face: 'Face') -> List['Face']:
        """
        Internal : inserts a face assuming the viability of the inserted face has been
        previously checked
        :param face:
        :return:
        """
        # check if the face can be inserted
        self.is_insertable(face)

        # add all pair edges to face
        face.add_exterior(self)

        # create a fixed list of the face edges for ulterior navigation
        self_edges = list(self.edges)

        # split the face edges if they touch a vertex of the container face
        # TODO : this is highly inefficient as we try to intersect every edge with every vertex
        # NOTE : per convention we do not modify the alignments of the receiving faces
        # this means that only the vertices and the edges of the inserted face can be modified
        # trough the snapping. If a vertex has to be created on an edge of the receiving face
        # it must be aligned with the existing edge.
        for _edge in face.edges:
            _edge.start.snap_to(*self.vertices)
            _edge.end.snap_to(*self.vertices)
            for _vertex in self.vertices:
                closest_point = project_point_on_segment(_vertex.coords, _edge.normal,
                                                         (_edge.start.coords, _edge.end.coords),
                                                         no_direction=True)
                dist = distance(_vertex.coords, closest_point) if closest_point else math.inf
                if dist <= COORD_EPSILON:
                    _edge.split(_vertex)

        # snap face vertices to edges of the container face
        # for performance purpose we store the snapped vertices and the corresponding edge
        shared_edges = []
        face_edges = list(face.edges)
        for edge in face_edges:
            vertex = edge.start
            vertex.edge = edge  # we need to do this to ensure proper snapping direction
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

    def _insert_face_over_internal_edge(self,
                                        face: 'Face',
                                        internal_edges: List[Edge]) -> List['Face']:
        """
        Inserts a face that overlaps an internal edge of the receiving face.
        This is hard.
        we have to :
        1. split the face,
        2. insert each newly created faces
        3. merge the inserted faces
        4. preserve the initial face reference
        TODO : extend this technique to enable the insertion of a face overlapping several faces
        TODO : we're adding the same face to the exterior
        :param face:
        :return:
        """
        logging.debug("Mesh: Inserting a face over an internal edge")

        # we slice the face if needed, we check each internal edges
        face_copy = face.swap()
        sliced_faces = [face_copy]
        for internal_edge in internal_edges:
            sliced_faces_temp = sliced_faces[:]
            for sliced_face in sliced_faces_temp:
                sliced_faces.remove(sliced_face)  # to prevent duplicates
                sliced_faces += sliced_face.slice(internal_edge.start, internal_edge.vector)

        # if no face was created we proceed with a standard insert
        # note this should not really happen
        if len(sliced_faces) == 1:
            face_copy.swap(face)
            return self._insert_face(face)

        logging.debug('Mesh: Inserting face in a face overlapping an internal edge')
        # else add each new face
        # first store the shared edges for ulterior merge
        edges_to_remove = []
        for sliced_face in sliced_faces:
            for edge in sliced_face.edges:
                if edge.pair.face in sliced_faces:
                    edges_to_remove.append(edge)

        # we create brand new faces and we insert them in the face
        # a bit brutal, a better way is certainly possible ;-)
        new_faces = []
        for sliced_face in sliced_faces:
            new_face = self.mesh.new_face_from_boundary(sliced_face.coords)
            new_faces.append(new_face)
            self.mesh.remove_face_and_children(sliced_face)

        # insert the new faces in the containing face
        # Note : we have to try for each face created
        container_faces = [self]
        for new_face in new_faces:
            container_faces_copy = container_faces[:]
            for container_face in container_faces_copy:
                try:
                    new_inserted_faces = container_face._insert_face(new_face)
                    container_faces.remove(container_face)
                    container_faces += new_inserted_faces
                    break
                except OutsideFaceError:
                    continue
            else:
                raise Exception("Could not insert the sliced face: this should never happen!!")

        # merge the faces
        remaining_face = new_faces[0]
        edges_to_remove = [e for new_face in new_faces
                           for e in new_face.edges if e.pair.face in new_faces]
        for edge in edges_to_remove:
            if not edge.mesh:  # we check if the edge has already been removed
                continue
            if edge.pair.face in new_faces:
                # we must not clean vertices to prevent the deletion of an edge on
                # which we are currently iterating thus creating an infinite loop
                remaining_face = edge.remove(clean_vertex=False)

        # we clean the vertices afterwards
        for vertex in list(remaining_face.vertices):
            vertex.clean()
        # attribute the references to the initial face
        # to preserve the face references
        remaining_face.swap(face)

        # return the create faces
        created_faces = sorted(container_faces, key=attrgetter('area'), reverse=True)

        return created_faces

    def insert_face(self, face: 'Face') -> List['Face']:
        """
        Inserts the face if it fits inside the receiving face
        Returns the list of the faces created inside the receiving face
        including the receiving face
        """
        mesh = self.mesh
        # check if the face can be inserted
        self.is_insertable(face)

        # Check if the receiving face has an internal edge because this is a very special
        # case and has to be treated differently
        internal_edges = list(self.internal_edges)
        intersects_an_internal_edge = False
        for edge in internal_edges:
            if edge.as_sp.intersects(face.as_sp_eroded):
                intersects_an_internal_edge = True
                break

        if intersects_an_internal_edge:
            created_faces = self._insert_face_over_internal_edge(face, internal_edges)
        else:
            created_faces = self._insert_face(face)

        # store the specific mesh operation
        receiving_face_was_deleted = True
        mesh.store_modification(MeshOps.INSERT, face, self)
        for created_face in created_faces:
            if created_face is self:
                receiving_face_was_deleted = False
                continue
            mesh.store_modification(MeshOps.INSERT, created_face, self)
        if receiving_face_was_deleted:
            mesh.store_modification(MeshOps.REMOVE, self)

        return created_faces

    def insert_face_from_boundary(self, perimeter: List[Coords2d]) -> List['Face']:
        """
        Inserts a face directly from a boundary
        :param perimeter:
        :return: the biggest face
        """
        face_to_insert = self.mesh.new_face_from_boundary(perimeter)
        try:
            new_faces = self.insert_face(face_to_insert)
            return new_faces
        except OutsideFaceError:
            self.mesh.remove_face_and_children(face_to_insert)
            raise

    def insert_crop_face_from_boundary(self, perimeter: [Coords2d]) -> ['Face']:
        """
        Inserts a face inside the receiving face and crops the face if necessary to include
        in receiving face
        NOTE : we do not insert face that will have a hole, or face that will be split into
        several polygons.
        :param perimeter:
        :return:
        """
        assert len(perimeter) >= 3, "The specified perimeter must have at least 3 points"
        face_polygon = Polygon(perimeter + [perimeter[0]])
        self_polygon = self.as_sp.buffer(0)

        if not face_polygon.is_valid or not self_polygon.is_valid:
            raise ValueError("Mesh: Insert and Crop: Badly formed polygons")

        intersection = face_polygon.intersection(self_polygon)

        if intersection.is_empty or intersection.geom_type != "Polygon":
            raise OutsideFaceError

        # to prevent crossing polygons we need to do this with shapely
        intersection.buffer(0)

        if intersection.area < COORD_EPSILON:
            logging.debug("Mesh: Insert and Crop: small intersection ignored")
            return []

        cropped_perimeter = intersection.exterior.coords[::-1]
        # remove the last point because shapely returns a looped structure
        cropped_perimeter.pop()
        # we need to remove duplicates because shapely will sometimes return weird things...
        # first we clean the perimeter by truncating the value to the project resolution
        cropped_perimeter = list(map(lambda x: (truncate(x[0]), truncate(x[1])), cropped_perimeter))
        # then we search for consecutive duplicates and remove them
        number_of_points = len(cropped_perimeter)
        duplicate_points = []
        for i in range(number_of_points):
            j = (i + 1) % number_of_points
            if distance(cropped_perimeter[j], cropped_perimeter[i]) < COORD_EPSILON:
                duplicate_points.append(cropped_perimeter[i])

        for duplicate in duplicate_points:
            cropped_perimeter.remove(duplicate)

        if len(cropped_perimeter) < 3:
            logging.debug("Mesh: Insert and Crop: The intersection has less than 3 points")
            return []

        return self.insert_face_from_boundary(cropped_perimeter)

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
                # clean unused vertex
                if not vertex_1.edge:
                    vertex_1.remove_from_mesh()
                if not vertex_2.edge:
                    vertex_2.remove_from_mesh()

                raise OutsideVertexError('Could not insert edge because vertex' +
                                         ' is not on the face boundary')
            self.mesh.watch()  # TODO this is ugly but necessary to correctly update the linear
            edges.append(edge)

        return edges[0]

    def merge(self, other: 'Face') -> Optional['Face']:
        """
        Merges two adjacent faces. In order to be merge they have to share at least one edge
        :param other:
        :return:
        """
        # find one shared edge and remove it
        # Note : the remove method will cleanup the other remaining edges
        for edge in self.edges:
            if edge.pair.face is other:
                shared_edge = edge
                return shared_edge.remove()

        logging.warning('Mesh: Cannot merge two faces that do not share at least one edge:%s - %s',
                        self, other)

    def clean(self):
        """
        Check if the face has only to edges. If this is the case :
        1. we merge the two edges
        2. we remove the face from the mesh
          --------- >
            edge_1
        •    Face    •
            edge_2
          < ---------
        :return:
        """
        if self.edge.next.next is not self.edge:
            return self

        logging.debug("Face: Cleaning a two faced faces")

        mesh = self.mesh

        edge_1 = self.edge
        edge_2 = self.edge.next
        # preserve the references
        edge_1.preserve_references(edge_2.pair)
        edge_2.preserve_references(edge_1.pair)
        # change the pair
        edge_1.pair.pair, edge_2.pair.pair = edge_2.pair, edge_1.pair

        # remove from the mesh the removed components : face and two edges
        edge_1.remove_from_mesh()
        edge_2.remove_from_mesh()
        self.remove_from_mesh()

        mesh.watch()

        return None

    def simplify(self) -> Sequence[Edge]:
        """
        Check if the end and start vertices of each edge are very close to themselves
        and snaps them if needed. If the face only has two edges, cleans the face.
        TODO : we should also clean isolated vertices
        :return: the modified edges
        """
        modified_edges = []
        cleaned_face = self.clean()
        if cleaned_face is None:
            return modified_edges
        for edge in self.edges:
            # 1. remove small edges
            if edge.length <= COORD_EPSILON:  # and edge.is_mutable
                small_edge = edge

                if not (edge.start.mutable or edge.end.mutable):
                    return modified_edges

                if not edge.start.mutable:
                    small_edge = edge
                else:
                    # pick the best edge to collapse to preserve edges alignment
                    angle = ccw_angle(edge.pair.previous.opposite_vector, edge.next.vector)
                    end_aligned = pseudo_equal(angle, 180.0, epsilon=ANGLE_EPSILON)

                    angle = ccw_angle(edge.previous.opposite_vector, edge.pair.next.vector)
                    start_aligned = pseudo_equal(angle, 180.0, epsilon=ANGLE_EPSILON)

                    if not end_aligned and start_aligned:
                        small_edge = edge.pair

                logging.debug('Mesh: Collapsing edge while simplifying face: %s', small_edge)
                small_edge.collapse()
                modified_edges.append(small_edge)
                modified_edges.append(small_edge.pair)
                modified_edges += self.simplify()
                break
        return modified_edges

    def recursive_simplify(self) -> Sequence[Edge]:
        """
        Simplify a face and all other modified faces
        :return:
        """
        modified_edges = self.simplify()
        total_modified_edges = modified_edges

        for edge in modified_edges:
            if edge.pair.face is not None:
                total_modified_edges += edge.pair.face.recursive_simplify()

        return total_modified_edges

    def number_of_corners(self) -> int:
        """
        returns the number of corners of the face
        :return:
        """
        corner_min_angle = 20.0
        num_corners = 0
        for edge in self.edges:
            angle = ccw_angle(edge.opposite_vector, edge.next.vector)
            if not pseudo_equal(angle, 180.0, corner_min_angle):
                num_corners += 1

        return num_corners

    def plot(self, ax=None,
             options=('fill', 'border'),
             color: Optional[str] = None,
             save: Optional[bool] = None,
             alpha: Optional[float] = 0.3):
        """
        Plots the face
        :return:
        """
        x, y = self.as_sp.exterior.xy
        return plot_polygon(ax, x, y, options, color, save, alpha)


class Mesh:
    """
    Mesh Class
    """

    def __init__(self, _id: Optional[int] = None):
        self._edge = None  # boundary edge of the mesh
        self._faces = {}
        self._edges = {}
        self._vertices = {}
        # Watchers
        self._watchers: [Callable[['MeshComponent', str], None]] = []
        self._modifications: Dict[int,
                                  Tuple['MeshOps', Tuple['MeshComponentType', int],
                                        Optional[Tuple['MeshComponentType', int]]]] = {}
        self.id = _id or uuid.uuid4()
        self._counter: int = 0

        # for caching purpose
        self._cached_area: Optional[float] = None

    def __repr__(self):
        output = 'Mesh:\n'
        for face in self.faces:
            output += face.__repr__() + '\n'
        return output + '-' * 24

    def clear(self):
        """
        Clears the data of the mesh
        :return:
        """
        self._edge = None
        self._faces = {}
        self._edges = {}
        self._vertices = {}
        self._watchers = []
        self._modifications = {}

    def get_id(self) -> int:
        """
        Returns a new incremental id for each component of the mesh
        :return:
        """
        self._counter += 1
        return self._counter

    def _reset_counter(self):
        """
        Reset the id counter to a proper value. Needed when deserializing a mesh.
        :return:
        """
        vertices_id = set(self._vertices.keys())
        faces_id = set(self._faces.keys())
        edges_id = set(self._edges.keys())
        self._counter = max(vertices_id | faces_id | edges_id)

    def compute_cache(self):
        """
        Computes the cached values for area / length of the mesh elements
        :return:
        """
        for face in self.faces:
            face.cached_area = face.area

    @property
    def components_id(self) -> Generator[int, None, None]:
        """
        Returns all the used id
        :return:
        """
        yield from (i for i in self._vertices)
        yield from (i for i in self._edges)
        yield from (i for i in self._faces)

    def serialize(self) -> Dict[str, Union[str, Dict[str, Tuple]]]:
        """
        Stores the mesh geometric data in a json structure
        The structure is as follow:
        {
            vertices: {id: (0.0, 012), id: (0.0, 0.13) ...}
            edges: {id: (start_id, next_id, pair_id, face_id), }
        }
        the face_id of the empty face is -1 per convention
        :return: a json
        """
        vertices = {vertex.id: vertex.coords for vertex in self.vertices}
        edges = {edge.id: [edge.start.id, edge.next.id, edge.pair.id,
                           edge.face.id if edge.face else ""] for edge in self.edges}
        output = {
            "id": str(self.id),
            "edge": self._edge.id if self._edge else "",  # not really needed
            "vertices": vertices,
            "edges": edges
        }

        return output

    def deserialize(self, value: Dict[str, Union[str, Dict[str, Tuple]]]) -> 'Mesh':
        """
        Creates the mesh from the input serialization value
        :param value:
        :return:
        """
        # make sure the mesh has no data
        self.clear()
        # preserve id reference
        self.id = uuid.UUID(value["id"])

        vertices = value["vertices"]
        edges = value["edges"]

        # create vertex
        for _id, point in vertices.items():
            _id = int(_id)
            Vertex(self, point[0], point[1], _id=_id)

        # create edges
        for _id, edge in edges.items():
            _id = int(_id)
            start_id = int(edge[0])
            face_id = int(edge[3]) if edge[3] else None
            start = self.get_vertex(start_id)
            edge = Edge(self, start, _id=_id)

            # add the edge of the vertex
            if not start.edge:
                start.edge = edge

            # add or create the face
            if face_id:
                if face_id in self._faces:
                    face = self.get_face(face_id)
                else:
                    face = Face(self, edge, face_id)
                edge.face = face

        # add pair and next
        for _id, edge in edges.items():
            edge_id = int(_id)
            next_id = int(edge[1])
            pair_id = int(edge[2])
            # We should find every edge
            edge = self.get_edge(edge_id)
            pair = self.get_edge(pair_id)
            next_edge = self.get_edge(next_id)
            edge.pair = pair
            edge.next = next_edge

        # add boundary edge
        if value["edge"]:
            edge_id = int(value["edge"])
            self.boundary_edge = self.get_edge(edge_id)

        self._reset_counter()

        return self

    def __getstate__(self) -> Dict:
        """
        Used to customize the pickling method. Needed due to the very circular natures of the
        half-edge data structure.
        :return: the data used for pickling
        """
        return self.serialize()

    def __setstate__(self, state: Dict):
        """
        Used to customize the pickling method. Needed due to the very circular natures of the
        half-edge data structure.
        :param state: the data used to unpickle
        """
        self.deserialize(state)

    def add_watcher(self, watcher: Callable[[Dict[int, MeshModification]], None]):
        """
        Adds a watcher to the mesh.
        Each time a mesh component is added or removed, a call to the watcher is triggered.
        The watcher must accept as argument a MeshComponent (eg: Vertex, Edge or Face) and a
        string indicating the type of mesh modification : "add" or "remove"
        :param watcher:
        :return:
        """
        if watcher in self._watchers:
            logging.debug("Mesh: Trying to add a watcher already bound with the mesh %s", self)
            return

        self._watchers.append(watcher)

    def store_modification(self,
                           op: 'MeshOps',
                           component: 'MeshComponent',
                           other_component: Optional['MeshComponent'] = None):
        """
        Adds a modification to the modifications list.
        We check for duplicates or reversed modification.
        Example :
        • add face n°1 + add face n°1 = add face n°1
        • add face n°1 + remove face n°1 = ø
        • remove face n°1 + remove face n°1 = raise Error
        • remove face n°1 + add face n°1 = raise Error
        :param component:
        :param other_component:
        :param op:
        :return:
        """
        if component.id in self._modifications:
            previous_op = self._modifications[component.id][1]
            if previous_op == MeshOps.REMOVE:
                raise ValueError("Impossible to modify a removed mesh component %s", component)
            if previous_op in (MeshOps.ADD, MeshOps.INSERT):
                if op == MeshOps.ADD:
                    # the component was already added no need to add a modification
                    return
                if op == MeshOps.REMOVE:
                    # the component was added then removed : both modification can be erased
                    del self._modifications[component.id]
                    return
                if op == MeshOps.INSERT:
                    # the component was added and inserted we can delete the previous op
                    # we do not want to keep both ops
                    del self._modifications[component.id]

        self._modifications[component.id] = (op, (component.type, component.id),
                                             (other_component.type if other_component else None,
                                              other_component.id if other_component else None))

    def watch(self):
        """
        Triggers the watcher on the modifications list
        :return:
        """
        for watcher in self._watchers:
            watcher(self._modifications, self.id)
        self._modifications = {}

    def add(self, component: Union['MeshComponent', 'Vertex', 'Face', 'Edge']):
        """
        Adds a mesh component to the mesh
        :param component:
        :return:
        """
        if component.id is None:
            component.id = self.get_id()

        self.store_modification(MeshOps.ADD, component)

        if type(component) == Vertex:
            self._add_vertex(component)

        if type(component) == Face:
            self._add_face(component)

        if type(component) == Edge:
            self._add_edge(component)

    def update(self, component):
        """
        Adds a mesh component to the mesh
        :param component:
        :return:
        """
        if type(component) == Vertex:
            self._add_vertex(component)

        if type(component) == Face:
            self._add_face(component)

        if type(component) == Edge:
            self._add_edge(component)

    def remove(self, component):
        """
        Adds a mesh component to the mesh
        :param component:
        :return:
        """

        if type(component) == Vertex:
            if component.id not in self._vertices:
                logging.debug("Mesh: Vertex is not in mesh")
                return
            self.store_modification(MeshOps.REMOVE, component)
            self._remove_vertex(component)

        elif type(component) == Face:
            if component.id not in self._faces:
                logging.warning("Mesh: face is not in mesh")
                return
            self.store_modification(MeshOps.REMOVE, component)
            self._remove_face(component)

        elif type(component) == Edge:
            if component.id not in self._edges:
                logging.debug("Mesh: Edge is not in mesh")
                return
            self.store_modification(MeshOps.REMOVE, component)
            self._remove_edge(component)

    def _add_face(self, face: 'Face'):
        """
        Adds a face to the mesh
        :param face:
        :return: self
        """
        self._faces[face.id] = face

    def _add_face_and_children(self, face: 'Face'):
        """
        Adds a face to the mesh and its children components
        :param face:
        :return:
        """
        assert face.edge, "you must provide a face with a reference edge"

        for edge in face.edges:
            self.add(edge)
            self.add(edge.pair)
            self.add(edge.start)

    def remove_face_and_children(self, face: 'Face'):
        """
        Removes from the mesh the face
        :param face:
        :return: self
        """
        if face.id not in self._faces:
            raise ValueError('Cannot remove the face that' +
                             ' is not already in the mesh, {0}'.format(face))

        for edge in face.edges:
            if edge.mesh:
                self.remove(edge)
            if edge.pair.mesh:
                self.remove(edge.pair)
            if edge.start.mesh:
                self.remove(edge.start)

        self.remove(face)

    def _remove_face(self, face: 'Face'):
        """
        Removes from the mesh the face
        :param face:
        :return: self
        """
        del self._faces[face.id]
        face.mesh = None

    def get_face(self, _id: int) -> 'Face':
        """
        Returns the face with the given id
        :param _id:
        :return: a face
        """
        return self._faces[_id]

    def has_face(self, _id: int) -> bool:
        """
        Returns True if the specified face id belongs to the mesh
        :param _id: id of the desired face
        :return: True or False
        """
        return _id in self._faces

    def _add_edge(self, edge: 'Edge'):
        """
        Adds an edge to the mesh
        :param edge:
        :return:
        """
        self._edges[edge.id] = edge

    def _remove_edge(self, edge: 'Edge'):
        """
        Adds an edge to the mesh
        :param edge:
        :return:
        """
        del self._edges[edge.id]
        edge.mesh = None

    def get_edge(self, edge_id: int) -> 'Edge':
        """
        Gets the edge of the provided id
        :param edge_id:
        :return:
        """
        return self._edges[edge_id]

    def has_edge(self, _id: int) -> bool:
        """
        Returns True if the specified edge id belongs to the mesh
        :param _id: id of the desired edge
        :return: True or False
        """
        return _id in self._edges

    def _add_vertex(self, vertex: Vertex):
        """
        Adds a vertex to the mesh storage
        :param vertex:
        :return:
        """
        self._vertices[vertex.id] = vertex

    def _remove_vertex(self, vertex: Vertex):
        """
        Removes a vertex from the mesh structure
        :param vertex:
        :return:
        """
        del self._vertices[vertex.id]
        vertex.mesh = None

    def get_vertex(self, vertex_id: int) -> Vertex:
        """
        Returns the specified vertex
        :param vertex_id:
        :return:
        """
        return self._vertices[vertex_id]

    def has_vertex(self, _id: int) -> bool:
        """
        Returns True if the specified vertex id belongs to the mesh
        :param _id: id of the desired vertex
        :return: True or False
        """
        return _id in self._vertices

    @property
    def faces(self) -> List['Face']:
        """
        property
        :return: the faces of the mesh
        """
        return list(face for _, face in self._faces.items())

    def new_face_from_boundary(self, boundary: Sequence[Coords2d]) -> 'Face':
        """
        Creates a new face from a boundary
        :return:
        """
        logging.debug("Mesh: Creating new face from boundary")

        assert len(boundary) > 2, ("To form a face a boundary "
                                   "of at least three points must be provided: {}".format(boundary))

        # check if the perimeter respects the ccw rotation
        # we use shapely LinearRing object
        sp_perimeter = LinearRing(boundary)
        if not sp_perimeter.is_ccw:
            raise ValueError('The perimeter is not ccw:{0}'.format(boundary))
        if not sp_perimeter.is_simple:
            raise ValueError('The perimeter crosses itself:{0}'.format(boundary))

        initial_vertex = Vertex(self, boundary[0][0], boundary[0][1], mutable=False)
        initial_edge = Edge(self, initial_vertex)
        initial_face = Face(self, initial_edge)

        initial_edge.face = initial_face
        initial_vertex.edge = initial_edge

        previous_edge = initial_edge
        previous_pair_edge = None

        for point in boundary[1:]:
            new_vertex = Vertex(self, point[0], point[1])

            new_edge = Edge(self, new_vertex, face=initial_face)
            new_vertex.edge = new_edge

            previous_edge.next = new_edge
            new_pair_edge = Edge(self, new_vertex, previous_pair_edge, pair=previous_edge)

            previous_pair_edge = new_pair_edge
            previous_edge = new_edge

        previous_edge.next = initial_edge
        new_pair_edge = Edge(self, initial_vertex, previous_pair_edge, previous_edge)
        initial_edge.pair.next = new_pair_edge

        return initial_face

    @property
    def edges(self) -> Generator[Edge, None, None]:
        """
        property
        :return: the edges of the mesh
        """
        return (edge for edge in self._edges.values())

    @property
    def vertices(self) -> Generator[Vertex, None, None]:
        """
        Returns all the vertices of the mesh
        :return:
        """
        return (vertex for vertex in self._vertices.values())

    def check_duplicate_vertices(self) -> bool:
        """
        Check if there are duplicates vertices. Same coordinates but not same vertex.
        :return:
        """
        is_valid = True
        for vertex in self.vertices:
            for other_vertex in self.vertices:
                if other_vertex is vertex:
                    continue
                if other_vertex.distance_to(vertex) < COORD_EPSILON / 4:
                    logging.info('Mesh: Found duplicate vertices: ' +
                                 '{0} - {1}'.format(vertex, other_vertex))
                    is_valid = True  # Turn this off waiting for better snapping handling
        return is_valid

    @property
    def boundary_edge(self) -> Edge:
        """
        property
        :return: one of the external edge of the mesh
        """
        return self._edge

    @boundary_edge.setter
    def boundary_edge(self, value: Edge):
        """
        property
        Sets the external edge of the mesh
        """
        if value.face is not None:
            raise ValueError('An external edge cannot have a face: {0}'.format(value))
        self._edge = value

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
    def boundary_as_sp(self):
        """"
        Returns the mesh boundary as a Shapely LinearRing
        """
        vertices = []
        edge = None
        for edge in self.boundary_edges:
            vertices.append(edge.start.coords)
        return LinearRing(vertices[::-1]) if edge else None

    @property
    def as_sp(self):
        """
        Returns a polygon covering the mesh
        :return:
        """
        return Polygon(self.boundary_as_sp)

    def area(self, cache: bool = False):
        """
        Returns the area of the mesh
        :return:
        """
        if cache and self._cached_area is not None:
            return self._cached_area
        else:
            self._cached_area = self.as_sp.area
            return self._cached_area

    # noinspection PyTypeChecker
    # There seems to be a bug in Typing for .items() of a typed Dict
    @property
    def directions(self) -> List[Tuple[float, float]]:
        """
        Returns the main directions of the mesh as a tuple containing an angle and a length
        For each boundary edge we calculate the absolute ccw angle and we add it to a dict
        :return:
        """
        directions_dict: Dict[float, float] = {}

        for edge in self.boundary_edges:
            # TODO : this should be coherent with ANGLE_EPSILON and not just an integer round
            angle = float(round(edge.absolute_angle % 180.0))
            if angle in directions_dict:
                directions_dict[angle] += edge.length
            else:
                directions_dict[angle] = edge.length

        return sorted(directions_dict.items(), key=itemgetter(1), reverse=True)

    def simplify(self):
        """
        Simplifies the mesh by snapping close vertices to each other
        :return:
        """
        modified_edges = []
        for face in self.faces:
            modified_edges += face.recursive_simplify()

        return modified_edges

    def insert_external_face(self, face: 'Face'):
        """
        Inserts an outside face in the mesh.
        The face cannot be contained by the mesh or an
        OutsideFaceError will be raised.

        TODO : We should replace the None face with a face of type Exterior
               to enable more isomorphic code. This would also enable the proper
               representation of a mesh with a hole

        :param face: the face to add to the mesh
        :return: void
        """
        if not self.as_sp.disjoint(face.as_sp_eroded):
            raise OutsideFaceError("Mesh: The face should be on the exterior of the mesh :%s", face)

        # create a fixed list of the face edges for ulterior navigation
        boundary_edges = list(self.boundary_edges)

        # snap the external vertices of the mesh to the face edges
        for edge in self.boundary_edges:
            vertex = edge.start
            face_edges = list(face.edges)
            new_edge = vertex.snap_to_edge(*face_edges)
            if new_edge is not None:
                logging.debug('Mesh: Snapped a vertex from the receiving face: %s', vertex)

        # snap face vertices to edges of the container face
        # for performance purpose we store the snapped vertices and the corresponding edge
        shared_edges = []
        face_edges = list(face.edges)
        for edge in face_edges:
            vertex = edge.start
            vertex.edge = edge  # we need to do this to ensure proper snapping direction
            edge_shared = vertex.snap_to_edge(*boundary_edges)
            if edge_shared is not None:
                shared_edges.append((edge_shared, edge))
                # after a split: update list of edges
                boundary_edges = list(self.boundary_edges)

        # the face should have at least one edge in common with the mesh
        if not shared_edges:
            raise ValueError("Mesh: Cannot add a face that is not adjacent to the mesh: %s", face)

        touching_edge, edge, new_face = None, None, None
        # NB: touching_edge is the edge on the container face
        all_faces = []

        # connect the edges together
        for shared in shared_edges:
            # touching edge is on the boundary of the mesh, edge is inside the face
            touching_edge, edge = shared
            previous_edge = edge.previous
            previous_touching_edge = touching_edge.previous

            # connect the correct edges
            previous_touching_edge.next = previous_edge.pair
            edge.pair.next = touching_edge

            # insure proper mesh boundary edge reference
            self.boundary_edge = touching_edge

            # backward check for isolation
            # first check for 2-edged face
            # if a 2 edged face is found we keep the edge and remove the touching edge
            # we preserve id for eventual references
            if previous_edge.pair.next.next is previous_edge.pair:
                # preserve references for face and vertex
                previous_edge.pair.preserve_references(previous_edge.pair.next.pair)
                previous_edge.pair.next.preserve_references(previous_edge)
                # remove the edge from the mesh
                previous_edge.pair.remove_from_mesh()
                # remove the duplicate edges
                previous_edge.pair = previous_edge.pair.next.pair
                # swap the id to preserve references
                previous_edge.swap_id(previous_touching_edge)
                # remove the edge from the mesh
                previous_touching_edge.remove_from_mesh()

            # else check for new face creation
            elif previous_edge.pair not in self.boundary_edges:
                new_face = Face(self, previous_edge.pair)
                all_faces.append(new_face)
                for orphan_edge in previous_edge.pair.siblings:
                    orphan_edge.face = new_face

        # forward check : at the end of the loop check forward for isolation
        if edge.pair.next.next is edge.pair:
            # remove from the mesh
            edge.pair.remove_from_mesh()
            edge.pair = touching_edge.pair
            # swap the id to preserve references
            edge.swap_id(touching_edge)
            # remove the edge from the mesh
            touching_edge.remove_from_mesh()
            # find the new exterior face
            for face in all_faces:
                if not face.as_sp_linear_ring.is_ccw:
                    for edge in face.edges:
                        edge.face = None
                    self.boundary_edge = edge
                    all_faces.remove(face)
                    face.remove_from_mesh()
                    break
            else:
                raise Exception("Mesh: A boundary face should have been found !!")

        return all_faces

    def check(self) -> bool:
        """
        Checks if the mesh is correctly formed.
        It's a best effort. Only a few strong consistencies are checked.
        :return: boolean
        """
        is_valid = True
        edges_id = []
        vertices_id = []

        for face in self.faces:
            # check for correct form
            face_polygon = face.as_sp.buffer(0)
            if not face_polygon.is_simple or not face_polygon.is_valid:
                logging.error("Mesh: face is not a simple polygon: %s", face)
                is_valid = False

            for edge in face.edges:
                if edge is None:
                    is_valid = False
                    logging.error('Mesh: Checking Mesh: Edge is None for:{0}'.format(face))
                    return is_valid
                edges_id.append(edge.id)
                vertices_id.append(edge.start.id)
                # check if all component are correctly stored in mesh
                if edge.id not in self._edges:
                    is_valid = False
                    logging.error("Mesh: Edge id not stored in mesh for edge: %s", edge)
                if edge.start.id not in self._vertices:
                    is_valid = False
                    logging.error("Mesh: Vertex id not stored in mesh for vertex: %s", edge.start)
                if edge.pair.id not in self._edges:
                    is_valid = False
                    logging.error("Mesh: Edge id not stored in mesh for edge: %s", edge.pair)

                if edge.face is not face:
                    is_valid = False
                    logging.error('Mesh: Checking Mesh: Wrong face in edge:' +
                                  '{0} for face:{1}'.format(edge, edge.face))
                if edge.pair and edge.pair.pair is not edge:
                    is_valid = False
                    logging.error('Mesh: Checking Mesh: Wrong pair attribution:' +
                                  ' {0} for face: {1}'.format(edge, edge.pair))
                if edge.start.edge is None:
                    is_valid = False
                    logging.error('Mesh: Checking Mesh: Vertex has no edge: {0}'.format(edge.start))
                if edge.start.edge is None or edge.start.edge.start is not edge.start:
                    is_valid = False
                    logging.error('Mesh: Checking Mesh: Wrong edge attribution in: ' +
                                  '{0} - {1}'.format(edge.start, edge))
                if edge.next.next is edge:
                    is_valid = False
                    logging.error('Mesh: Checking Mesh: 2-edges face found:{0}'.format(edge))
                if edge.next is edge.pair:
                    is_valid = False
                    logging.warning('Mesh: Checking Mesh: folded edge found: {0}'.format(edge))

        for edge in self.boundary_edges:
            edges_id.append(edge.id)
            vertices_id.append(edge.start.id)
            if edge.face is not None:
                logging.error('Mesh: Wrong edge in mesh boundary edges:{0}'.format(edge))
                is_valid = False

        is_valid = is_valid and self.check_duplicate_vertices()

        for vertex in self.vertices:
            if vertex.edge not in self.edges:
                logging.error("Mesh: Vertex has a reference edge outside of the mesh:"
                              "{} - {}".format(vertex, vertex.edge))
                is_valid = False

        for edge_id in self._edges:
            if edge_id not in edges_id:
                is_valid = False
                logging.error('Mesh: an extraneous edge was '
                              'found in the mesh structure: %s', self._edges[edge_id])

        for vertex_id in self._vertices:
            if vertex_id not in vertices_id:
                is_valid = False
                logging.error('Mesh: an extraneous vertex was '
                              'found in the mesh structure: %s', self._vertices[vertex_id])

        # check for overlapping pb
        faces_area = sum(face.area for face in self.faces)
        mesh_area = self.as_sp.area
        if not pseudo_equal(faces_area, mesh_area, COORD_EPSILON ** 2):
            logging.error("Mesh: Faces are overlapping, total face area %s, total mesh area %s",
                          faces_area, mesh_area)
            is_valid = False

        logging.info('Mesh: Checking Mesh: ' + ('✅ OK' if is_valid else '❌ KO'))
        return is_valid

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
        self.clear()
        new_face = self.new_face_from_boundary(boundary)
        self.boundary_edge = new_face.edge.pair

        return self

    @staticmethod
    def connected(faces: List['Face'], min_adjacency_length: Optional[float] = None) -> bool:
        """
        Return True if all the faces are connected
        :param faces:
        :param min_adjacency_length:
        """
        if not faces:
            return True

        current = faces[0]
        faces = set(faces)
        parent = {current: None}
        while current:
            for f in current.siblings(min_adjacency_length):
                if f is current:
                    continue
                if f not in faces:
                    continue
                if f not in parent:
                    parent[f] = current
                    current = f
                    break
            else:
                current = parent[current]

        return len(parent) == len(faces)
