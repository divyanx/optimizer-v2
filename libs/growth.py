# coding=utf-8
"""
Grow methods module
"""

from typing import TYPE_CHECKING, Optional, Callable, Generator, Sequence, Union

from libs.utils.geometry import ccw_angle, pseudo_equal, opposite_vector

if TYPE_CHECKING:
    from libs.seed import Seed
    from libs.mesh import Face
    from libs.plan import Space
    from libs.selector import Selector
    from libs.mutation import Mutation


GrowthSelector = Callable[['Seed'], Generator['Face', None, None]]


class GrowthMethod:
    """
    A method for growing a seed
    """
    def __init__(self, name: str, action: Optional[GrowthSelector] = None,
                 selector: Optional['Selector'] = None,
                 mutation: Optional['Mutation'] = None):
        self.name = name
        self.action = action  # an action must take a seed as an argument and return a face
        self.selector = selector
        self.mutation = mutation

    def __call__(self, *args, **kwargs) -> Sequence['Space']:
        if self.action is None:
            return
        yield from self.action(args[0])


# Growth methods

def oriented_faces(direction: str, epsilon: float = 10.0) -> GrowthSelector:
    """
    Selector factory
    Returns an horizontal or a vertical face
    :param direction:
    :param epsilon:
    :return:
    """
    if direction not in ('horizontal', 'vertical'):
        raise ValueError('A direction can only be horizontal or vertical: {0}'.format(direction))

    def _selector(seed: 'Seed') -> Generator['Face', None, None]:
        space = seed.space
        vectors = ((seed.edge.unit_vector, opposite_vector(seed.edge.unit_vector))
                   if direction == 'horizontal' else
                   (seed.edge.normal,))

        for vector in vectors:
            edges_list = [edge for edge in space.edges
                          if pseudo_equal(ccw_angle(edge.normal, vector), 180.0, epsilon)]
            for edge in edges_list:
                face = edge.pair.face
                if face is None:
                    continue
                yield face

    return _selector


def surround_faces(seed: 'Seed') -> Generator['Face', None, None]:
    """
    Returns the faces around the specified space
    :param seed:
    :return:
    """
    component = seed.components[0]
    for edge in component.edges:
        face = edge.pair.face
        if face is None or face.space is seed.space:
            continue
        # find a shared edge with the space
        for face_edge in face.edges:
            if face_edge.pair.space is seed.space:
                break
        else:
            continue
        yield face
        break


def any_faces(seed: 'Seed') -> Generator['Face', None, None]:
    """
    Returns any face around the seed space
    :param seed:
    :return:
    """
    for edge in seed.space.edges:
        if edge.pair.face and edge.pair.face.space is not seed.space:
            yield edge.pair.face
            break


GROWTH_METHODS = {
    'horizontal_growth': GrowthMethod('horizontal', oriented_faces('horizontal')),
    'vertical_growth': GrowthMethod('horizontal', oriented_faces('vertical')),
    'surround_growth': GrowthMethod('surround', surround_faces),
    'free_growth': GrowthMethod('free', any_faces),
    'done': GrowthMethod('done')
}
