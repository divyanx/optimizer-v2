"""
Refiner Test Module
"""

import logging
import pytest
import time

from libs.refiner.refiner import REFINERS
from libs.read_write import reader_test

import tools.cache

INPUT_FILES = reader_test.BLUEPRINT_INPUT_FILES

PARAMS = {"ngen": 50, "mu": 20, "cxpb": 0.2, "processes": 4}


@pytest.mark.parametrize("input_file", INPUT_FILES)
def refiner_simple(input_file):
    """
    Test refiner on all plan files
    051 / 009 / 062 / 055
    :return:
    """
    logging.getLogger().setLevel(logging.INFO)
    plan_number = input_file[:len(input_file) - 5]

    sol = tools.cache.get_solution(plan_number, grid="001", seeder="directional_seeder")

    if sol:
        plan = sol.spec.plan
        plan.name = "original" + "_" + plan_number
        plan.remove_null_spaces()
        plan.plot()

        # run genetic algorithm
        start = time.time()
        improved_plan = REFINERS["nsga"].apply_to(sol, PARAMS).spec.plan
        end = time.time()
        improved_plan.name = "Refined_" + plan_number
        improved_plan.plot()

        # analyse found solutions
        logging.info("Time elapsed: {}".format(end - start))
        logging.info("Solution found : {} - {}".format(improved_plan.fitness.wvalue,
                                                       improved_plan.fitness.values))

        assert improved_plan.check()
