# coding=utf-8
"""
Finisher module :
Applies a genetic algorithm to improve the plan according to several constraints :
• rooms sizes
• rooms shapes
• circulation [TO DO]

The module is inspired by the DEAP library (global toolbox for genetic algorithms :
https://github.com/deap/deap)

It implements a simple version of the NSGA-II algorithm:

    [Deb2002] Deb, Pratab, Agarwal, and Meyarivan, "A fast elitist
    non-dominated sorting genetic algorithm for multi-objective
    optimization: NSGA-II", 2002.

TODO LIST:
    • refine grid prior to genetic search
    • create efficient all aligned edges mutation
    • check edge selector to make sure we are not eliminating needed scenarios
    • add similar function to create diversity in the hof

"""
import random
import logging
import multiprocessing

from typing import TYPE_CHECKING, Optional, Callable, List, Union, Tuple
from libs.plan.plan import Plan

from libs.refiner import core, crossover, evaluation, mutation, nsga, population, support

if TYPE_CHECKING:
    from libs.specification.specification import Specification
    from libs.refiner.core import Individual

# The type of an algorithm function
algorithmFunc = Callable[['core.Toolbox', Plan, Optional['support.HallOfFame']],
                         List['core.Individual']]


class Refiner:
    """
    Refiner Class.
    A refiner will try to improve the plan using a genetic algorithm.
    The refiner is composed of a :
    • Toolbox factory that will create the toolbox
    containing the main types and operators needed for the algorithm
    • the algorithm function that will be applied to the plan
    """
    def __init__(self,
                 fc_toolbox: Callable[['Specification'], 'core.Toolbox'],
                 algorithm: algorithmFunc):
        self._toolbox_factory = fc_toolbox
        self._algorithm = algorithm

    def apply_to(self, plan: 'Plan', spec: 'Specification') -> 'Plan':
        """
        Applies the refiner to the plan and returns the result.
        :param plan:
        :param spec:
        :return:
        """
        results = self.run(plan, spec)
        return max(results, key=lambda i: i.fitness)

    def run(self,
            plan: 'Plan',
            spec: 'Specification',
            processes: int = 1,
            with_hof: bool = False) -> Union[List['core.Individual'], 'support.HallOfFame']:
        """
        Runs the algorithm and returns the results
        :param plan:
        :param spec:
        :param processes: The number of processes to fork (if equal to 1: no multiprocessing
                          is used.
        :param with_hof: whether to return the results or a hall of fame
        :return:
        """
        _hof = support.HallOfFame(4, lambda a, b: a.is_similar(b)) if with_hof else None
        # 1. refine mesh of the plan
        # TODO : implement this

        # 2. create plan cache for performance reason
        for floor in plan.floors.values():
            floor.mesh.compute_cache()

        plan.store_meshes_globally()  # needed for multiprocessing (must be donne after the caching)
        toolbox = self._toolbox_factory(spec)

        # NOTE : the pool must be created after the toolbox in order to
        # pass the global objects created when configuring the toolbox
        # to the forked processes
        map_func = multiprocessing.Pool(processes=processes).map if processes > 1 else map
        toolbox.register("map", map_func)

        # 3. run the algorithm
        initial_ind = toolbox.individual(plan)
        results = self._algorithm(toolbox, initial_ind, _hof)

        output = results if not with_hof else _hof
        toolbox.evaluate_pop(toolbox.map, toolbox.evaluate, output)
        return output


# Toolbox factories

# Algorithm functions
def mate_and_mutate(mate_func,
                    mutate_func,
                    params,
                    couple: Tuple['Individual', 'Individual']) -> Tuple['Individual', 'Individual']:
    """
    Specific function for nsga algorithm
    :param mate_func:
    :param mutate_func:
    :param params: a dict containing the arguments of the function
    :param couple:
    :return:
    """
    cxpb = params["cxpb"]
    _ind1, _ind2 = couple
    if random.random() <= cxpb:
        mate_func(_ind1, _ind2)
    mutate_func(_ind1)
    mutate_func(_ind2)
    _ind1.fitness.clear()
    _ind2.fitness.clear()

    return _ind1, _ind2


def fc_nsga_toolbox(spec: 'Specification') -> 'core.Toolbox':
    """
    Returns a toolbox
    :param spec: The specification to follow
    :return: a configured toolbox
    """
    toolbox = core.Toolbox()
    toolbox.configure("fitness", "CustomFitness", (-3.0, -2.0, -3.0))
    toolbox.configure("individual", "customIndividual", toolbox.fitness)
    # Note : order is very important as tuples are evaluated lexicographically in python
    scores_fc = [evaluation.score_corner,
                 evaluation.score_bounding_box,
                 evaluation.fc_score_area]
    toolbox.register("evaluate", evaluation.compose, scores_fc, spec)
    toolbox.register("mutate", mutation.mutate_simple)
    toolbox.register("mate", crossover.connected_differences)
    toolbox.register("mate_and_mutate", mate_and_mutate, toolbox.mate, toolbox.mutate,
                     {"cxpb": 0.8})
    toolbox.register("select", nsga.select_nsga)
    toolbox.register("populate", population.fc_mutate(toolbox.mutate))

    return toolbox


def simple_ga(toolbox: 'core.Toolbox',
              initial_ind: 'core.Individual',
              hof: Optional['support.HallOfFame']) -> List['core.Individual']:
    """
    A simple implementation of a genetic algorithm.
    :param toolbox: a refiner toolbox
    :param initial_ind: an initial individual
    :param hof: an optional hall of fame to store best individuals
    :return: the best plan
    """
    # algorithm parameters
    ngen = 100
    mu = 100  # Must be a multiple of 4 for tournament selection of NSGA-II

    pop = toolbox.populate(initial_ind, mu)
    toolbox.evaluate_pop(toolbox.map, toolbox.evaluate, pop)

    # This is just to assign the crowding distance to the individuals
    # no actual selection is done
    pop = toolbox.select(pop, len(pop))

    # Begin the generational process
    for gen in range(1, ngen):
        logging.info("Refiner: generation %i : %f prct", gen, gen / ngen * 100.0)
        # Vary the population
        offspring = nsga.select_tournament_dcd(pop, len(pop))
        offspring = [toolbox.clone(ind) for ind in offspring]

        # note : list is needed because map lazy evaluates
        modified = list(toolbox.map(toolbox.mate_and_mutate, zip(offspring[::2], offspring[1::2])))
        offspring = [i for t in modified for i in t]

        # Evaluate the individuals with an invalid fitness
        toolbox.evaluate_pop(toolbox.map, toolbox.evaluate, offspring)

        # Select the next generation population
        pop = toolbox.select(pop + offspring, mu)

        # store best individuals in hof
        if hof is not None:
            hof.update(pop)

    return pop


REFINERS = {
    "simple": Refiner(fc_nsga_toolbox, simple_ga)
}
