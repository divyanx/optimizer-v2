# coding=utf-8
"""
Reader module : Used to read file from json input and create a plan.
"""
from typing import Dict, Sequence, Tuple
import os
import json

import libs.plan as plan
from libs.category import space_categories, linear_categories

from libs.utils.geometry import (
    point_dict_to_tuple,
    barycenter,
    direction_vector,
    normal,
    move_point
)
from libs.utils.custom_types import Coords2d, FourCoords2d


INPUT_FOLDER = "../resources/blueprints"
INPUT_FILES = [
    "Antony_A22.json",
    "Antony_A33.json",
    "Antony_B14.json",
    "Antony_B22.json",
    "Bussy_A001.json",
    "Bussy_A101.json",
    "Bussy_A202.json",
    "Bussy_B104.json",
    "Levallois_Parisot.json",
    "Levallois_A3_505.json",
    "Levallois_Creuze.json",
    "Massy_C102.json",
    "Massy_C204.json",
    "Noisy_A318.json",
    "Paris18_A402.json",
    "Paris18_A502.json",
    "Sartrouville_A104.json",
    "Sartrouville_R1.json",
    "Vernouillet_A002.json",
    "Vernouillet_A105.json",
    "Edison_10.json",
    "Edison_20.json",
]


def get_perimeter(input_floor_plan_dict: Dict) -> Sequence[Coords2d]:
    """
    Returns a vertices list of the perimeter points of an apartment
    :param input_floor_plan_dict:
    :return:
    """
    apartment = input_floor_plan_dict['apartment']
    perimeter_walls = apartment['externalWalls']
    vertices = apartment['vertices']
    return [(vertices[i]['x'], vertices[i]['y']) for i in perimeter_walls]


def get_fixed_item_perimeter(fixed_item: Dict,
                             vertices: Sequence[Coords2d]) -> FourCoords2d:
    """calculates the polygon perimeter of the fixed item
    Input dict expected with following attributes
    Should be useless if the dict gives us the fixed item geometry directly
    {
        "type": "doorWindow",
        "vertex2": 1,
        "width": 80,
        "coef1": 286,
        "vertex1": 0,
        "coef2": 540
      },
    """
    width = fixed_item['width']
    vertex_1 = point_dict_to_tuple(vertices[fixed_item['vertex1']])
    vertex_2 = point_dict_to_tuple(vertices[fixed_item['vertex2']])
    coef_1 = fixed_item['coef1']
    coef_2 = fixed_item['coef2']
    point_1 = barycenter(vertex_1, vertex_2, coef_1 / 1000)
    point_2 = barycenter(vertex_1, vertex_2, coef_2 / 1000)

    vector = direction_vector(point_1, point_2)
    normal_vector = normal(vector)

    point_3 = move_point(point_2, normal_vector, width)
    point_4 = move_point(point_1, normal_vector, width)

    return point_1, point_2, point_3, point_4


def get_fixed_items_perimeters(input_floor_plan_dict: Dict) -> Sequence[Tuple[Coords2d, Dict]]:
    """
    Returns a list with the perimeter of each fixed items.
    NOTE: we are using the pandas dataframe because we do not want to recalculate
    the absolute geometry of each fixed items. As a general rule,
    it would be much better to read and store the geometry
    of each fixed items as list of vertices instead of the way it's done by using barycentric and
    width data. It would be faster and enable us any fixed item shape.
    :param input_floor_plan_dict:
    :return: list
    """
    apartment = input_floor_plan_dict['apartment']
    vertices = apartment['vertices']
    fixed_items = apartment['fixedItems']
    output = []
    for fixed_item in fixed_items:
        coords = get_fixed_item_perimeter(fixed_item, vertices)
        output.append((coords, fixed_item['type']))

    return output


def get_floor_plan_dict(file_path: str = 'Antony_A22.json') -> Dict:
    """
    Retrieves the data dictionary from an optimizer json input
    :return:
    """

    module_path = os.path.dirname(__file__)
    input_file_path = os.path.join(module_path, INPUT_FOLDER, file_path)

    # retrieve data from json file
    with open(os.path.abspath(input_file_path)) as floor_plan_file:
        input_floor_plan_dict = json.load(floor_plan_file)

    return input_floor_plan_dict


def create_plan_from_file(input_file: str) -> plan.Plan:
    """
    Creates a plan object from the data retrieved from the given file
    :param input_file: the path to a json file
    :return: a plan object
    """
    floor_plan_dict = get_floor_plan_dict(input_file)
    perimeter = get_perimeter(floor_plan_dict)

    my_plan = plan.Plan().from_boundary(perimeter)
    empty_space = my_plan.empty_space

    fixed_items = get_fixed_items_perimeters(floor_plan_dict)

    for fixed_item in fixed_items:
        if fixed_item[1] in space_categories:
            empty_space.insert_space(fixed_item[0], category=space_categories[fixed_item[1]])
        if fixed_item[1] in linear_categories:
            empty_space.insert_linear(fixed_item[0][0], fixed_item[0][1],
                                      category=linear_categories[fixed_item[1]])

    return my_plan