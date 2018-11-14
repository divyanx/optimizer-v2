# coding=utf-8
"""
Category module : describes the type of space or linear that can be used in a program or a plan.
"""

CATEGORIES_COLORS = {
    'duct': 'k',
    'loadBearingWall': 'k',
    'window': '#FFCB19',
    'doorWindow': '#FFCB19',
    'entrance': 'r',
    'frontDoor': 'r',
    'empty': 'b',
    'space': 'b',
    'seed': '#6a006a'
}


class Category:
    """
    A category of a space or a linear
    """
    def __init__(self, name: str, mutable: bool = True, seedable: bool = False, color: str = 'b'):
        self.name = name
        self.mutable = mutable
        self.seedable = seedable
        self.color = CATEGORIES_COLORS.get(self.name, color)

    def __repr__(self):
        return self.name


class SpaceCategory(Category):
    """
    A category of a space
    Examples: duct, chamber, kitchen, wc, bathroom, entrance
    """
    pass


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
        self.mutable = mutable

# TODO : we should create a catalog class that encapsulates the different categories


linear_categories = {
    'window': LinearCategory('window', False, True, True),
    'door': LinearCategory('door', aperture=True),
    'doorWindow': LinearCategory('doorWindow', False, True, True),
    'frontDoor': LinearCategory('frontDoor', False, True, True),
    'wall': LinearCategory('wall'),
    'externalWall': LinearCategory('externalWall', False, width=2.0)
}

space_categories = {
    'empty': SpaceCategory('empty'),
    'seed': SpaceCategory('seed'),
    'duct': SpaceCategory('duct', False, True),
    'loadBearingWall': SpaceCategory('loadBearingWall', False),
    'chamber': SpaceCategory('chamber'),
    'bedroom': SpaceCategory('bedroom'),
    'living': SpaceCategory('living'),
    'entrance': SpaceCategory('entrance'),
    'kitchen': SpaceCategory('kitchen'),
    'bathroom': SpaceCategory('bathroom'),
    'wcBathroom': SpaceCategory('wcBathroom'),
    'livingKitchen': SpaceCategory('livingKitchen'),
    'wc': SpaceCategory('wc')
}
