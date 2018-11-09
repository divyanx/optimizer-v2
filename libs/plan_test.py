# coding=utf-8

"""
Test module for plan module
"""

import pytest

from libs.plan import Plan
from libs.category import space_categories
import libs.logsetup as ls
import libs.reader as reader


ls.init()

INPUT_FILES = reader.BLUEPRINT_INPUT_FILES


@pytest.mark.parametrize("input_file", INPUT_FILES)
def test_floor_plan(input_file):
    """
    Test. We create a simple grid on several real blue prints.
    :return:
    """
    plan = reader.create_plan_from_file(input_file)

    for empty_space in plan.empty_spaces:
        boundary_edges = list(empty_space.edges)
        
        for edge in boundary_edges:
            if edge.length > 30:
                empty_space.barycenter_cut(edge, 0)
                empty_space.barycenter_cut(edge, 1)

    assert plan.check()


def test_add_duct_to_space():
    """
    Test. Add various space inside an emptySpace.
    We test different cases such as an internal duct, a touching duct etc.
    TODO : split this in several tests.
    :return:
    """

    perimeter = [(0, 0), (1000, 0), (1000, 1000), (0, 1000)]
    duct = [(200, 0), (400, 0), (400, 400), (200, 400)]

    duct_category = space_categories['duct']

    # add border duct
    plan = Plan().from_boundary(perimeter)
    plan.insert_space_from_boundary(duct, duct_category)

    # add inside duct
    inside_duct = [(600, 200), (800, 200), (800, 400), (600, 400)]
    plan.insert_space_from_boundary(inside_duct, duct_category)

    # add touching duct
    touching_duct = [(0, 800), (200, 800), (200, 1000), (0, 1000)]
    plan.insert_space_from_boundary(touching_duct, duct_category)

    # add separating duct
    separating_duct = [(700, 800), (1000, 700), (1000, 800), (800, 1000), (700, 1000)]
    plan.insert_space_from_boundary(separating_duct, duct_category)

    # add single touching point
    point_duct = [(0, 600), (200, 500), (200, 700)]
    plan.insert_space_from_boundary(point_duct, duct_category)

    # add complex duct
    complex_duct = [(300, 1000), (300, 600), (600, 600), (600, 800), (500, 1000),
                    (450, 800), (400, 1000), (350, 1000)]
    plan.insert_space_from_boundary(complex_duct, duct_category)

    assert plan.check()


def test_add_face():
    """
    Test. Create a new face, remove it, then add it again.
    :return:
    """
    perimeter = [(0, 0), (1000, 0), (1000, 1000), (0, 1000)]

    plan = Plan().from_boundary(perimeter)

    complex_face = [(700, 800), (1000, 700), (1000, 800), (800, 1000), (700, 1000)]
    plan.empty_space.face.insert_face_from_boundary(complex_face)

    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    plan.empty_space.add_face(face_to_remove)

    assert plan.check()


def test_cut_to_inside_space():
    """
    Test a cut to a space inside another space.
    The cut should stop and not cut the internal space
    :return:
    """
    perimeter = [(0, 0), (1000, 0), (1000, 1000), (0, 1000)]
    plan = Plan().from_boundary(perimeter)
    duct = [(200, 200), (800, 200), (800, 800), (200, 800)]
    plan.insert_space_from_boundary(duct, space_categories['duct'])
    plan.empty_space.barycenter_cut(list(plan.empty_space.edges)[7])

    assert plan.check()


def test_add_overlapping_face():
    """
    Test. Create a new face, remove it, then add it again.
    :return:
    """
    perimeter = [(0, 0), (500, 0), (500, 500), (0, 500)]
    hole = [(200, 200), (300, 200), (300, 300), (200, 300)]
    hole_2 = [(50, 150), (150, 150), (150, 300), (50, 300)]

    plan = Plan().from_boundary(perimeter)

    plan.empty_space.face.insert_face_from_boundary(hole)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    plan.empty_space.face.insert_face_from_boundary(hole_2)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    assert plan.check()


def test_add_border_overlapping_face():
    """
    Test. Create a new face, remove it, then add it again.
    :return:
    """
    perimeter = [(0, 0), (500, 0), (500, 500), (0, 500)]
    hole = [(200, 200), (300, 200), (300, 300), (200, 300)]
    hole_2 = [(0, 150), (150, 150), (150, 300), (0, 300)]

    plan = Plan().from_boundary(perimeter)

    plan.empty_space.face.insert_face_from_boundary(hole)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    plan.empty_space.face.insert_face_from_boundary(hole_2)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    assert plan.check()


def test_add_face_touching_internal_edge():
    """
    Test. Create a new face, remove it, then add it again.
    :return:
    """
    perimeter = [(0, 0), (500, 0), (500, 500), (0, 500)]
    hole = [(200, 200), (300, 200), (300, 300), (200, 300)]
    hole_2 = [(50, 150), (150, 150), (150, 200), (50, 200)]
    hole_3 = [(50, 200), (150, 200), (150, 300), (50, 300)]

    plan = Plan().from_boundary(perimeter)

    plan.empty_space.face.insert_face_from_boundary(hole)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    plan.empty_space.face.insert_face_from_boundary(hole_2)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    plan.empty_space.face.insert_face_from_boundary(hole_3)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    assert plan.check()


def test_add_two_face_touching_internal_edge_and_border():
    """
    Test. Create a new face, remove it, then add it again.
    :return:
    """
    perimeter = [(0, 0), (500, 0), (500, 500), (0, 500)]
    hole = [(200, 200), (300, 200), (300, 300), (200, 300)]
    hole_2 = [(0, 150), (150, 150), (150, 200), (0, 200)]
    hole_3 = [(0, 200), (150, 200), (150, 300), (0, 300)]

    plan = Plan().from_boundary(perimeter)

    plan.empty_space.face.insert_face_from_boundary(hole)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    plan.empty_space.face.insert_face_from_boundary(hole_2)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    plan.empty_space.face.insert_face_from_boundary(hole_3)
    face_to_remove = list(plan.empty_space.faces)[1]
    plan.empty_space.remove_face(face_to_remove)

    assert plan.check()


def test_insert_separating_wall():
    """
    Test
    :return:
    """
    perimeter = [(0, 0), (500, 0), (500, 500), (0, 500)]
    wall = [(250, 0), (300, 0), (300, 500), (250, 500)]
    plan = Plan('Plan_test_wall').from_boundary(perimeter)

    plan.insert_space_from_boundary(wall, category=space_categories['loadBearingWall'])

    assert plan.check()
