# coding=utf-8
"""
Circulation module

used to detect isolated rooms and generate a path to connect them

"""

import logging
from typing import Dict, List, Tuple
from libs.plan import Space, Plan, Vertex
from libs.mesh import Edge
from libs.plot import plot_save
from libs.utils.graph import Graph_nx, EdgeGraph
from libs.category import LINEAR_CATEGORIES


# TODO : deal with load bearing walls by defining locations where they can be crossed

class Circulator:
    """
    Circulator Class
    contains utilities to detect isolated rooms connect them to circulation spaces
    """

    def __init__(self, plan: Plan, cost_rules: Dict = None):
        self.plan = plan
        self.path_calculator = PathCalculator(plan=self.plan, cost_rules=cost_rules)
        self.path_calculator.build()
        self.connectivity_graph = Graph_nx()
        self.connecting_paths = {level: [] for level in plan.list_level}
        self.circulation_cost = 0

    def draw_path(self, space1: Space, space2: Space) -> Tuple['List[Vertex]', float]:
        """
        Finds the shortest path between two spaces in the plan
        :return list of vertices on the path and cost of the path
        """
        graph = self.path_calculator.graph
        path_min = None
        cost_min = None
        # tests all possible connections between both spaces
        # TODO : that's brutal, any more clever way to connect two sub graphs
        for edge1 in space1.edges:
            for edge2 in space2.edges:
                path, cost = graph.get_shortest_path(edge1, edge2)
                if cost_min is None or cost < cost_min:
                    cost_min = cost
                    path_min = path

        return path_min, cost_min

    def multilevel_connection(self):
        """
        in multi-lvel case, adds a connection between spaces containing the stair at each level
        """
        number_of_floors = self.plan.floor_count
        space_connection_between_floors = []

        if number_of_floors > 1:
            for level in self.plan.list_level:
                for space in self.plan.spaces:
                    if space.floor.level is level and "startingStep" in space.components_category_associated():
                        space_connection_between_floors.append(space)
                        break

        for i in range(number_of_floors - 1):
            self.connectivity_graph.add_edge(space_connection_between_floors[i],
                                             space_connection_between_floors[i + 1])

    def init_connectivity_graph(self):
        """
        builds a connectivity graph of the plan, each circulation space is a node
        :return:
        """

        for space in self.plan.circulation_spaces():
            self.connectivity_graph.add_node(space)

        # builds connectivity graph for circulation spaces
        for space in self.plan.circulation_spaces():
            for other in self.plan.circulation_spaces():
                if other is not space and other.adjacent_to(space):
                    # if spaces are adjacent, they are connected in the graph
                    self.connectivity_graph.add_edge(space, other)

        self.multilevel_connection()

        self.set_circulation_path()

    def expand_connectivity_graph(self):
        """
        connects each non circulation space of the plan to a circulation space
        :return:
        """
        for space in self.plan.mutable_spaces():
            if space not in self.connectivity_graph.nodes():
                self.connectivity_graph.add_node(space)
                for other in self.plan.circulation_spaces():
                    if other is not space and other.adjacent_to(space):
                        self.connectivity_graph.add_edge(space, other)

        for node in list(self.connectivity_graph.nodes()):
            if not self.connectivity_graph.node_connected(node):
                connected_room = self.connect_space_to_circulation_graph(node)
                self.connectivity_graph.add_edge(connected_room, node)

    def set_circulation_path(self):
        """
        ensures circulation spaces are all connected
        :return:
        """

        father_nodes = {}

        for room in self.plan.mutable_spaces():
            if room.category.name is 'entrance':
                father_nodes[room.floor.level] = room
                break
        else:
            for room in self.plan.mutable_spaces():
                if room.category.name is 'living':
                    father_nodes[room.floor.level] = room
                    break

        if not father_nodes:
            return True

        start_level = list(father_nodes.keys())[0]

        father_node = [room for room in self.plan.spaces if
                       room.floor.level is not start_level and "startingStep"
                       in room.components_category_associated()]

        for f in father_node:
            father_nodes[f.floor.level] = f

        for node in self.connectivity_graph.nodes():
            if not self.connectivity_graph.has_path(node, father_nodes[node.floor.level]):
                path, cost = self.draw_path(father_nodes[node.floor.level], node)
                self.circulation_cost += cost
                self.actualize_path(path,node.floor.level)
                self.connectivity_graph.add_edge(node, father_nodes[node.floor.level])

    def actualize_path(self, path: List, level: int):
        """
        update based on computed corridor path
        :return:
        """
        self.connecting_paths[level].append(path)
        # when a circulation has been set, it can be used to connect every other spaces
        # without cost increase
        self.path_calculator.set_corridor_to_zero_cost(path)

    def connect_space_to_circulation_graph(self, space):
        """
        connects the given space with a circulation space of the plan
        :return:
        """
        path_min = None
        connected_room = None
        cost_min = None
        for other in self.plan.circulation_spaces():
            if other is not space and space.floor.level is other.floor.level:
                path, cost = self.draw_path(space, other)
                if cost_min is None or cost < cost_min:
                    cost_min = cost
                    path_min = path
                    connected_room = other
        if path_min is not None:
            self.actualize_path(path_min, space.floor.level)
            self.circulation_cost += cost_min

        return connected_room

    def connect(self):
        """
        detects isolated rooms and generate a path to connect them
        :return:
        """
        self.init_connectivity_graph()
        self.expand_connectivity_graph()

    def plot(self, show: bool = False, save: bool = True):
        """
        plots plan with circulation paths
        :return:
        """

        ax = self.plan.plot(show=show, save=False)

        number_of_floors = self.plan.floor_count

        for i in range(number_of_floors):
            _ax = ax[i]
            paths = self.connecting_paths[i]
            for path in paths:
                if len(path) == 1:
                    _ax.scatter(path[0].x, path[0].y, marker='o', s=15, facecolor='blue')
                else:
                    for i in range(len(path) - 1):
                        v1 = path[i]
                        v2 = path[i + 1]
                        x_coords = [v1.x, v2.x]
                        y_coords = [v1.y, v2.y]
                        _ax.plot(x_coords, y_coords, 'k',
                                 linewidth=2,
                                 color="blue",
                                 solid_capstyle='butt')

        plot_save(save, show)


class PathCalculator:
    """
    PathCalculator class
    builds and manages a graph that can be used by a circulator so as to compute shortest path
    between two spaces independant from the library used to build the graph
    """

    def __init__(self, plan: Plan, cost_rules: Dict = None, graph_lib: str = 'Dijkstar'):
        self.plan = plan
        self.graph_lib = graph_lib
        self.graph = None
        self.cost_rules = cost_rules

        window_cat = [cat for cat in LINEAR_CATEGORIES.keys() if
                      LINEAR_CATEGORIES[cat].window_type]
        self.component_edges = {'duct_edges': self.plan.category_edges('duct'),
                                'window_edges': self.plan.category_edges(*window_cat)}

    def __repr__(self):
        output = 'Grapher:\n'
        output += 'graph library :' + self.graph_lib + '\n'
        return output

    def build(self):
        """
        runs through space edges and adds branches to the graph, for each branch computes a weight
        :return:
        """
        self.graph = EdgeGraph(self.graph_lib)
        graph = self.graph
        graph.init()

        for space in self.plan.spaces:
            if space.mutable:
                self._update(space)

        graph.set_cost_function()

    def _update(self, space: Space):
        """
        add edge to the graph and computes its cost
        return:
        """
        graph = self.graph
        for edge in space.edges:
            cost = self.cost(edge, space)
            graph.add_edge(edge, cost)

    def set_corridor_to_zero_cost(self, path):
        """
        sets the const of circulation edges to zero
        :return:
        """
        nb_vert = len(path)
        if nb_vert > 1:
            for v in range(nb_vert - 1):
                vert1 = path[v]
                vert2 = path[v + 1]
                self.graph.add_edge_by_vert(vert1, vert2, 0)

            self.graph.set_cost_function()

    def rule_type(self, edge: Edge, space: Space) -> str:
        """
        gets the rule for edge cost computation
        :return: float
        """
        rule = 'default'

        num_ducts = space.count_ducts()
        num_windows = space.count_windows()

        if (edge.pair and edge.pair in self.component_edges['duct_edges']
                and list(needed_space for needed_space in space.category.needed_spaces if
                         needed_space.name is 'duct')):
            if num_ducts <= 2:
                rule = 'water_room_less_than_two_ducts'
            else:
                rule = 'water_room_default'


        elif (edge in self.component_edges['window_edges'] and list(
                needed_linear for needed_linear in space.category.needed_linears if
                needed_linear.window_type)):
            if num_windows <= 2:
                rule = 'window_room_less_than_two_windows'
            else:
                rule = 'window_room_default'

        return rule

    def cost(self, edge: Edge, space: Space) -> float:
        """
        computes the cost of an edge
        :return: float
        """
        cost = edge.length / 100

        rule = self.rule_type(edge, space)
        # rule='default'
        if rule not in self.cost_rules.keys():
            raise ValueError('The rule dict does not contain this rule {0}'.format(rule))
        cost += self.cost_rules[rule]

        return cost

    def get_shortest_path(self, edge1: Edge, edge2: Edge) -> Tuple['List[Vertex]', float]:
        """
        get the shortest path between two edges
        :return list of vertices on the path and cost of the path
        """
        graph = self.graph
        return graph.get_shortest_path(self, edge1, edge2)


COST_RULES = {
    'water_room_less_than_two_ducts': 10e5,
    'water_room_default': 1000,
    'window_room_less_than_two_windows': 10e10,
    'window_room_default': 5000,
    'default': 0
}

if __name__ == '__main__':
    import libs.reader as reader
    from libs.seed import Seeder, GROWTH_METHODS, FILL_METHODS_HOMOGENEOUS
    from libs.selector import SELECTORS
    from libs.grid import GRIDS
    from libs.shuffle import SHUFFLES
    from libs.space_planner import SpacePlanner
    from category import SPACE_CATEGORIES
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--plan_index", help="choose plan index",
                        default=0)

    args = parser.parse_args()
    plan_index = int(args.plan_index)

    logging.getLogger().setLevel(logging.DEBUG)


    def test_duplex():
        """
        Test
        :return:
        """
        boundaries = [(0, 500), (400, 500), (400, 0), (1500, 0), (1500, 700), (1000, 700),
                      (1000, 800),
                      (0, 800)]
        boundaries_2 = [(0, 500), (400, 500), (400, 400), (1000, 400), (1000, 800), (0, 800)]

        plan = Plan("Solution_Tests_Multiple_floors")
        floor_1 = plan.add_floor_from_boundary(boundaries, floor_level=0)
        floor_2 = plan.add_floor_from_boundary(boundaries_2, floor_level=1)

        terrace_coords = [(400, 400), (400, 200), (1300, 200), (1300, 700), (1000, 700),
                          (1000, 400)]
        plan.insert_space_from_boundary(terrace_coords, SPACE_CATEGORIES["terrace"], floor_1)
        garden_coords = [(400, 200), (400, 0), (1500, 0), (1500, 700), (1300, 700), (1300, 200)]
        plan.insert_space_from_boundary(garden_coords, SPACE_CATEGORIES["garden"], floor_1)
        duct_coords = [(350, 500), (400, 500), (400, 520), (350, 520)]
        plan.insert_space_from_boundary(duct_coords, SPACE_CATEGORIES["duct"], floor_1)
        duct_coords = [(350, 780), (400, 780), (400, 800), (350, 800)]
        plan.insert_space_from_boundary(duct_coords, SPACE_CATEGORIES["duct"], floor_1)
        hole_coords = [(400, 700), (650, 700), (650, 800), (400, 800)]
        plan.insert_space_from_boundary(hole_coords, SPACE_CATEGORIES["hole"], floor_1)
        plan.insert_linear((650, 800), (650, 700), LINEAR_CATEGORIES["startingStep"], floor_1)
        plan.insert_linear((275, 500), (340, 500), LINEAR_CATEGORIES["frontDoor"], floor_1)
        plan.insert_linear((550, 400), (750, 400), LINEAR_CATEGORIES["doorWindow"], floor_1)
        plan.insert_linear((1000, 450), (1000, 650), LINEAR_CATEGORIES["doorWindow"], floor_1)
        plan.insert_linear((0, 700), (0, 600), LINEAR_CATEGORIES["window"], floor_1)

        duct_coords = [(350, 500), (400, 500), (400, 520), (350, 520)]
        plan.insert_space_from_boundary(duct_coords, SPACE_CATEGORIES["duct"], floor_2)
        duct_coords = [(350, 780), (400, 780), (400, 800), (350, 800)]
        plan.insert_space_from_boundary(duct_coords, SPACE_CATEGORIES["duct"], floor_2)
        hole_coords = [(400, 700), (650, 700), (650, 800), (400, 800)]
        plan.insert_space_from_boundary(hole_coords, SPACE_CATEGORIES["hole"], floor_2)
        plan.insert_linear((650, 800), (650, 700), LINEAR_CATEGORIES["startingStep"], floor_2)
        plan.insert_linear((500, 400), (600, 400), LINEAR_CATEGORIES["window"], floor_2)
        plan.insert_linear((1000, 550), (1000, 650), LINEAR_CATEGORIES["window"], floor_2)
        plan.insert_linear((0, 700), (0, 600), LINEAR_CATEGORIES["window"], floor_2)

        GRIDS["sequence_grid"].apply_to(plan)

        plan.plot()

        seeder = Seeder(plan, GROWTH_METHODS).add_condition(SELECTORS['seed_duct'], 'duct')
        (seeder.plant()
         .grow(show=True)
         .shuffle(SHUFFLES['seed_square_shape_component_aligned'], show=True)
         .fill(FILL_METHODS_HOMOGENEOUS, (SELECTORS["farthest_couple_middle_space_area_min_100000"],
                                          "empty"), show=True)
         .fill(FILL_METHODS_HOMOGENEOUS, (SELECTORS["single_edge"], "empty"), recursive=True,
               show=True)
         .simplify(SELECTORS["fuse_small_cell_without_components"], show=True)
         .shuffle(SHUFFLES['seed_square_shape_component_aligned'], show=True)
         .empty(SELECTORS["corner_big_cell_area_70000"])
         .fill(FILL_METHODS_HOMOGENEOUS, (SELECTORS["farthest_couple_middle_space_area_min_50000"],
                                          "empty"), show=True)
         .simplify(SELECTORS["fuse_small_cell_without_components"], show=True)
         .shuffle(SHUFFLES['seed_square_shape_component_aligned'], show=True))

        plan.plot()

        spec = reader.create_specification_from_file("test_solution_duplex_setup.json")
        spec.plan = plan

        space_planner = SpacePlanner("test", spec)
        space_planner.solution_research()

        return space_planner


    def connect_plan():
        """
        Test
        :return:
        """

        space_planner = test_duplex()

        if space_planner.solutions_collector.solutions:
            for solution in space_planner.solutions_collector.best():
                circulator = Circulator(plan=solution.plan, cost_rules=COST_RULES)
                circulator.connect()
                circulator.plot()
                logging.debug('connecting paths: {0}'.format(circulator.connecting_paths))


    connect_plan()
