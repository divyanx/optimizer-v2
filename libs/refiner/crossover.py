# coding=utf-8
"""
Genetic Algorithm Crossover module
A cross-over takes two individuals as input and returns two blended individuals
The individuals are modified in place
"""
import random
from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from libs.refiner.core import Individual


def connected_differences(ind_1: 'Individual', ind_2: 'Individual'):
    """
    Blends the two plans.
    For each floor :
    1. Finds every face that is different between the two individuals.
    2. Pick a random face amongst them
    3. Select all connected different faces
    4. Swaps their corresponding spaces between the two plans
    NOTE : we must check for "corner stone" situation where the removal of the faces will
    split the spaces in half... If a corner stone is found, we do nothing.
    :param ind_1:
    :param ind_2:
    :return: a tuple of the blended individual
    """
    if not ind_1 or not ind_2:
        return ind_1, ind_2
    for floor in ind_1.floors.values():
        differences = [f for f in floor.mesh.faces
                       if ind_1.get_space_of_face(f).id != ind_2.get_space_of_face(f).id]

        if len(differences) <= 1:
            # nothing to do
            continue

        # pick a random face and find all different faces connected to it
        seed_face = random.choice(differences)
        connected_faces = {seed_face}
        differences.remove(seed_face)
        while True:
            connections = set([f for f in differences for o in connected_faces if o.is_adjacent(f)])
            for f in connections:
                differences.remove(f)
                connected_faces.add(f)
            if not connections:
                break

        connected_faces = list(connected_faces)
        impacted_spaces_ind_1 = [ind_1.get_space_of_face(f) for f in connected_faces]
        impacted_spaces_ind_2 = [ind_2.get_space_of_face(f) for f in connected_faces]

        for space in set(impacted_spaces_ind_1) | set(impacted_spaces_ind_2):
            faces = list(filter(lambda f: space.has_face(f), connected_faces))
            if space.corner_stone(*faces):
                logging.debug("Crossover: No crossover possible")
                return ind_1, ind_2

        modified_spaces = []
        for i, face in enumerate(connected_faces):
            space_1 = impacted_spaces_ind_1[i]
            space_2 = impacted_spaces_ind_2[i]
            other_1 = ind_1.get_space_from_id(space_2.id)
            other_2 = ind_2.get_space_from_id(space_1.id)

            space_1.remove_face_id(face.id)
            other_1.add_face_id(face.id)

            space_2.remove_face_id(face.id)
            other_2.add_face_id(face.id)

            for space in [space_1, space_2, other_1, other_2]:
                if space not in modified_spaces:
                    modified_spaces.append(space)

        # make sure the plan structure is correct
        for space in modified_spaces:
            space.set_edges()

        return ind_1, ind_2


__all__ = ['connected_differences']