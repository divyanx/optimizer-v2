from typing import (
    TYPE_CHECKING,
    Sequence,
    Tuple,
    Optional,
    Dict
)
from libs.utils.geometry import (ccw_angle,
                                 unit,
                                 barycenter,
                                 rotate,
                                 minimum_rotated_rectangle,
                                 move_point)
from libs.plan.category import SpaceCategory, SPACE_CATEGORIES
from libs.io.plot import plot_polygon

if TYPE_CHECKING:
    from libs.utils.custom_types import FourCoords2d, Vector2d, Coords2d, ListCoords2d
    from libs.plan.plan import Space
    from libs.space_planner.solution import Solution

# custom type: order
# ex: (SPACE_CATEGORIES["bathroom"], "m", ("bathtub", "sink"), True) -> last bool is for PRM
Order = Tuple[SpaceCategory, str, Tuple[str, ...], bool]


class Garnisher:
    """
    Instanciates and fits furniture in plan with rooms.
    """

    def __init__(self, name: str, orders: Sequence[Order]):
        self.name = name
        self.orders = orders

    def apply_to(self, solution: 'Solution') -> None:
        """
        Modify the solution plan by applying the successive orders.
        """
        for order in self.orders:
            self._apply_order(solution, order)

    def _apply_order(self, solution: 'Solution', order: Order) -> None:
        """
        Apply an order by updating plan list of furniture and fitting them in space
        :param plan:
        :param
        :return:
        """
        category, variant, furniture_names, is_prm = order
        plan = solution.spec.plan
        for space in plan.mutable_spaces():
            item = solution.space_item[space]
            if item.category == category and item.variant == variant:
                furnitures = [Furniture(next(furniture
                                             for furniture in FURNITURE_CATALOG[name]
                                             if furniture.is_prm == is_prm))
                              # today only 1st one is picked
                              for name in furniture_names]
                self._fit(space, furnitures)
                for furniture in furnitures:
                    plan.furnitures.setdefault(space, []).append(furniture)

    def _fit(self, space: 'Space', furnitures: Sequence['Furniture']):
        for furniture in furnitures:
            fit_bed_in_bedroom(furniture, space)


class FurnitureCategory:
    BY_NAME: Dict[str, 'FurnitureCategory'] = {}

    def __init__(self,
                 name: str,
                 polygon: 'ListCoords2d',
                 is_prm: bool):
        self.name = name
        self.polygon = polygon
        self.is_prm = is_prm
        FurnitureCategory.BY_NAME[name] = self


class Furniture:
    def __init__(self,
                 category: Optional[FurnitureCategory] = None,
                 ref_point: Optional['Coords2d'] = None,
                 ref_vect: Optional['Vector2d'] = None):
        self.category = category
        self.ref_point = ref_point if ref_point is not None else (0, 0)
        self.ref_vect = unit(ref_vect) if ref_vect is not None else (0, 1)

    @property
    def middle_point(self) -> 'Coords2d':
        footprint = self.footprint()
        return barycenter(footprint[0], footprint[1], 0.5)

    @middle_point.setter
    def middle_point(self, value: 'Coords2d'):
        vect = self.ref_point[0] - self.middle_point[0], self.ref_point[1] - self.middle_point[1]
        self.ref_point = move_point(value, vect)

    def bounding_box(self) -> 'FourCoords2d':
        """
        Rectangle shape of the furniture
        """
        return minimum_rotated_rectangle(self.footprint())

    def footprint(self) -> 'ListCoords2d':
        """
        Real shape of the furniture, well oriented and located
        """
        angle = ccw_angle((0, 1), self.ref_vect)
        trans_x, trans_y = self.ref_point
        rotated = rotate(self.category.polygon, self.category.polygon[0], angle)
        translated = tuple([(x + trans_x, y + trans_y)
                            for x, y in rotated])
        return translated

    def plot(self, ax=None,
             options=('fill', 'border'),
             save: Optional[bool] = None):
        """
        Plots the face
        :return:
        """
        color = "black"
        footprint = self.footprint()
        x = [p[0] for p in footprint]
        y = [p[1] for p in footprint]
        return plot_polygon(ax, x, y, options, color, save)

    def serialize(self) -> Dict:
        """
        Returns a serialized version of the furniture
        :return:
        """
        output = {
            "ref_point": list(self.ref_point),
            "ref_vect": list(self.ref_vect),
            "category": self.category.name
        }

        return output

    def deserialize(self, value: Dict) -> 'Furniture':
        """
        Fills the feature with serialized data.
        :return:
        """
        self.ref_point = tuple(value["ref_point"])
        self.ref_vect= tuple(value["ref_vect"])
        self.category = FurnitureCategory.BY_NAME[value["category"]]
        return self


FURNITURE_CATALOG = {
    "bed": (FurnitureCategory("bed", ((0, 0), (140, 0), (140, 190), (0, 190)), False),
            FurnitureCategory("bed_prm_1", ((0, 0), (320, 0), (320, 310), (0, 310)), True),
            FurnitureCategory("bed_prm_2", ((0, 0), (380, 0), (380, 280), (0, 280)), True)),
    "bathtub": (FurnitureCategory("bathtub", ((0, 0), (140, 0), (140, 190), (0, 190)), True))
}

GARNISHERS = {
    "default": Garnisher("default", [
        (SPACE_CATEGORIES["bedroom"], "xs", ("bed",), False),
        (SPACE_CATEGORIES["bedroom"], "s", ("bed",), False),
        (SPACE_CATEGORIES["bedroom"], "m", ("bed",), False),
        (SPACE_CATEGORIES["bedroom"], "l", ("bed",), True),
        (SPACE_CATEGORIES["bedroom"], "xl", ("bed",), True),
    ])
}


def fit_bed_in_bedroom(bed: Furniture, bedroom: 'Space'):
    """
    Move furniture to fit in space.
    :return:
    """
    components = bedroom.immutable_components()
    windows = [component
               for component in components
               if "indow" in component.category.name]
    window_edges = [window.edge
                    for window in windows]

    aligned_edges = bedroom.aligned_siblings(bedroom.edge)
    initial_edge = aligned_edges[0]
    start_edge = None
    longest_length = 0
    windows_lines = []

    # try longest line without window
    while start_edge is not initial_edge:
        start_edge = aligned_edges[0]
        end_edge = aligned_edges[-1]

        # check for window
        window_found = False
        for edge in window_edges:
            if edge in aligned_edges:
                windows_lines.append((start_edge.start.coords, end_edge.end.coords))
                window_found = True
                break

        if not window_found:
            length = start_edge.start.distance_to(end_edge.end)
            if not window_found and length > longest_length:
                longest_length = length
                bed.ref_vect = start_edge.normal
                bed.middle_point = barycenter(start_edge.start.coords, end_edge.end.coords, 0.5)

        aligned_edges = bedroom.aligned_siblings(bedroom.next_edge(end_edge))
        start_edge = aligned_edges[0]
