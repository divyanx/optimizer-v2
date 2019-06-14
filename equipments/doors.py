# coding=utf-8
"""
Door module
Puts doors in a plan

"""

import logging
from typing import List, Tuple
import matplotlib.pyplot as plt

from libs.plan.plan import Space, Plan, Edge, Vertex, Linear, LINEAR_CATEGORIES
from libs.io.plot import plot_save

from libs.utils.geometry import (
    parallel,
    move_point,
    dot_product
)

DOOR_WIDTH = 90

"""
process:
pour chaque pièce de circulation, placer les portes avec un espace de circulation adjacent
nb : 
couloir en priorité
si pas de couloir connecté
*connecter avec une pièce de circulation avec un ordre de priorité
    -entrée
    -salon
    -dining?
    
*fonctions :
    -place_doors(plan)
    -place_door(space1,space2)
"""


def place_doors(plan: 'Plan'):
    """
    places the foors in the plan following those steps
    0 - builds a connection graph
    1 - place doors for non isolated rooms
    :param plan:
    :return:
    """
    pass


def place_door(space1: 'Space', space2: 'Space'):
    """
    places a door between space1 and space2
    *sets the position of the door
    *sets the aperture direction
    :param space1:
    :param space2:
    :return:
    """

    def _is_edge_of_point(edge, point: 'Point'):
        vect1 = (point[0] - edge.start.coords[0], point[1] - edge.start.coords[1])
        vect2 = (point[0] - edge.end.coords[0], point[1] - edge.end.coords[1])
        return dot_product(vect1, vect2) < 0

    contact_edges = [edge for edge in space1.edges if edge.pair in space2.edges]

    start_index = None
    for e, edge in enumerate(contact_edges):
        if not space1.previous_edge(edge) in contact_edges:
            start_index = e
            break
    if not start_index == 0:
        contact_edges = contact_edges[start_index:] + contact_edges[:start_index - 1]

    lines = [[contact_edges[0]]]
    for edge in contact_edges[1:]:
        if parallel(lines[-1][-1].vector, edge.vector):
            lines[-1].append(edge)
        else:
            lines.append([edge])

    contact_line = sorted(lines, key=lambda x: sum(e.length for e in x))[-1]
    contact_length = contact_line[0].start.distance_to(contact_line[-1].end)
    door_edges = []
    if contact_length < DOOR_WIDTH:
        door_edges.append(contact_line[0])
    else:
        coeff_start = contact_length * 0.5 * (1 - DOOR_WIDTH / contact_length)
        coeff_end = contact_length * 0.5 * (1 + DOOR_WIDTH / contact_length)
        if coeff_start > 0 and coeff_end < contact_length:
            start_door_point = move_point(contact_line[0].start.coords, contact_line[0].unit_vector,
                                          coeff_start)
            end_door_point = move_point(contact_line[0].start.coords, contact_line[0].unit_vector,
                                        coeff_end)
            start_edge = list(e for e in contact_line if _is_edge_of_point(e, start_door_point))[0]
            end_edge = list(e for e in contact_line if _is_edge_of_point(e, end_door_point))[0]
            start_index = 0
            for e, edge in enumerate(contact_line):
                if edge is start_edge:
                    start_index = e
                    break
            while contact_line[start_index] is not end_edge:
                door_edges.append(contact_line[start_index])
                start_index += 1
            door_edges.append(end_edge)
            # if not door_edges:
            #    door_edges.append(start_edge)
        else:
            door_edges.append(contact_line[0])

    for door_edge in door_edges:
        Linear(space1.plan, space1.floor, door_edge, LINEAR_CATEGORIES["door"])


def plot(plan: 'Plan', save: bool = True):
    """
    plots plan with circulation paths
    :return:
    """

    ax = plan.plot(save=False)
    number_of_levels = plan.floor_count
    for level in range(number_of_levels):
        _ax = ax[level] if number_of_levels > 1 else ax
        for linear in plan.linears:
            if linear.floor.level is level and linear.category.name is "door":
                linear.edge.plot(ax=_ax, color='blue')

    plot_save(save)


# __all__ = []
#
#
if __name__ == '__main__':
    import argparse
    from libs.modelers.grid import GRIDS
    from libs.modelers.seed import SEEDERS
    from libs.modelers.corridor import Corridor, CORRIDOR_BUILDING_RULES
    from libs.specification.specification import Specification

    # logging.getLogger().setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--plan_index", help="choose plan index",
                        default=1)

    args = parser.parse_args()
    plan_index = int(args.plan_index)

    plan_name = None
    if plan_index < 10:
        plan_name = '00' + str(plan_index) + ".json"
    elif 10 <= plan_index < 100:
        plan_name = '0' + str(plan_index) + ".json"


    def get_plan(input_file: str = "001.json") -> Tuple['Plan', 'Specification']:

        import libs.io.reader as reader
        import libs.io.writer as writer
        from libs.space_planner.space_planner import SPACE_PLANNERS
        from libs.io.reader import DEFAULT_PLANS_OUTPUT_FOLDER

        folder = DEFAULT_PLANS_OUTPUT_FOLDER

        spec_file_name = input_file[:-5] + "_setup0"
        plan_file_name = input_file

        try:
            new_serialized_data = reader.get_plan_from_json(input_file)
            plan = Plan(input_file[:-5]).deserialize(new_serialized_data)
            spec_dict = reader.get_json_from_file(spec_file_name + ".json",
                                                  folder)
            spec = reader.create_specification_from_data(spec_dict, "new")
            spec.plan = plan
            return plan, spec

        except FileNotFoundError:
            plan = reader.create_plan_from_file(input_file)
            spec = reader.create_specification_from_file(input_file[:-5] + "_setup0" + ".json")

            GRIDS["002"].apply_to(plan)
            # GRIDS['optimal_finer_grid'].apply_to(plan)
            SEEDERS["directional_seeder"].apply_to(plan)
            spec.plan = plan

            space_planner = SPACE_PLANNERS["standard_space_planner"]
            best_solutions = space_planner.apply_to(spec, 3)

            new_spec = space_planner.spec

            if best_solutions:
                solution = best_solutions[0]
                plan = solution.plan
                new_spec.plan = plan
                writer.save_plan_as_json(plan.serialize(), plan_file_name)
                writer.save_as_json(new_spec.serialize(), folder, spec_file_name + ".json")
                return plan, new_spec
            else:
                logging.info("No solution for this plan")


    def main(input_file: str):

        # TODO : à reprendre
        # * 61 : wrong corridor shape

        out = get_plan(input_file)
        plan = out[0]
        spec = out[1]
        plan.name = input_file[:-5]

        # corridor = Corridor(layer_width=25, nb_layer=5)

        corridor = Corridor(corridor_rules=CORRIDOR_BUILDING_RULES["no_cut"]["corridor_rules"],
                            growth_method=CORRIDOR_BUILDING_RULES["no_cut"]["growth_method"])
        corridor.apply_to(plan, spec=spec, show=False)

        space1 = None
        space2 = None
        cat1 = "livingKitchen"
        cat2 = "bedroom"
        space1 = list(sp for sp in plan.spaces if
                      sp.category.name == cat1)[0]
        space2 = list(sp for sp in plan.spaces if
                      sp.category.name == cat2 and sp in space1.adjacent_spaces())[0]

        place_door(space1, space2)
        plot(plan)


    plan_name = "018.json"
    main(input_file=plan_name)
