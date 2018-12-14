# coding=utf-8
"""
Category module : describes the type of space or linear that can be used in a program or a plan.
"""
from libs.utils.catalog import Catalog

CATEGORIES_COLORS = {
    'duct': 'k',
    'loadBearingWall': 'k',
    'window': '#FFCB19',
    'doorWindow': '#FFCB19',
    'frontDoor': 'r',
    'empty': 'b',
    'space': 'b',
    'seed': '#6a006a',
    'living': 'aquamarine',
    'dining': 'turquoise',
    'kitchen': 'paleturquoise',
    'bedroom': 'mistyrose',  ''
    'wc': 'cornflowerblue',
    'bathroom': 'lightskyblue',
    'circulationSpace': 'lightgray',
    'entrance': 'r',
    'dressing': 'pink',
    'laundry': 'lightsteelblue',
    'office': 'darkseagreen',
    'misc':'lightsteelblue',
    'balcony': 'silver',
    'terrace': 'silver',
    'garden': 'green',
    'loggia': 'silver'
}


class Category:
    """
    A category of a space or a linear
    """
    def __init__(self,
                 name: str,
                 mutable: bool = True,
                 seedable: bool = False,
                 external: bool = False,
                 color: str = 'b'
                 ):
        self.name = name
        self.mutable = mutable
        self.seedable = seedable
        self.external = external
        self.color = CATEGORIES_COLORS.get(self.name, color)

    def __repr__(self) -> str:
        return self.name


class SpaceCategory(Category):
    """
    A category of a space
    Examples: duct, chamber, kitchen, wc, bathroom, entrance
    """
    def __init__(self,
                 name,
                 mutable: bool = True,
                 seedable: bool = False,
                 external: bool = False,
                 circulation: bool = False):
        super().__init__(name, mutable, seedable, external)
        self.circulation = circulation


class LinearCategory(Category):
    """
    A category of a linear
    Examples : window, doorWindow, door, wall, entrance
    """

    def __init__(self,
                 name,
                 mutable: bool = True,
                 seedable: bool = False,
                 aperture: bool = False,
                 width: float = 5.0):
        super().__init__(name, mutable, seedable)
        self.aperture = aperture
        self.width = width


LINEAR_CATEGORIES = Catalog('linears').add(
    LinearCategory('window', mutable=False, seedable=True, aperture=True),
    LinearCategory('door', aperture=True),
    LinearCategory('doorWindow', mutable=False, seedable=True, aperture=True),
    LinearCategory('frontDoor', mutable=False, seedable=True, aperture=True),
    LinearCategory('wall'),
    LinearCategory('externalWall', False, width=2.0))

SPACE_CATEGORIES = Catalog('spaces').add(
    SpaceCategory('empty'),
    SpaceCategory('seed'),
    SpaceCategory('duct', mutable=False, seedable=True),
    SpaceCategory('loadBearingWall', mutable=False),
    SpaceCategory('chamber'),
    SpaceCategory('bedroom'),
    SpaceCategory('living', circulation=True),
    SpaceCategory('entrance', circulation=True),
    SpaceCategory('kitchen'),
    SpaceCategory('bathroom'),
    SpaceCategory('dining', circulation=True),
    SpaceCategory('office'),
    SpaceCategory('dressing'),
    SpaceCategory('wc'),
    SpaceCategory('corridor', circulation=True),
    SpaceCategory('balcony', mutable=False, external=True),
    SpaceCategory('garden', mutable=False, external=True),
    SpaceCategory('terrace', mutable=False, external=True),
    SpaceCategory('loggia', mutable=False, external=True)
)
