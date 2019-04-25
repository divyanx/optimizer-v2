#!/usr/bin/env python3
import argparse
import logging
import os

import uuid
import requests

import sentry_sdk

import libpath

from libs.utils.executor import Executor
from libs.worker.config import Config
from libs.worker.core import TaskDefinition, TaskProcessor
from libs.worker.mq import Exchanger


# Initializing sentry at the earliest stage to detect any issue that might happen later
sentry_sdk.init("https://55bd31f3c51841e5b2233de2a02a9004@sentry.io/1438222", {
    'environment': os.getenv('HABX_ENV', 'local'),
    'release': Executor.VERSION,
})


def fetch_task_definition(context: dict) -> TaskDefinition:
    endpoint = 'https://www.habx-dev.fr/api/optimizer-v2/job'

    response = requests.get(endpoint, params=context)

    job_input = response.json()
    job_input['context']['taskId'] = str(uuid.uuid4())

    td = TaskDefinition.from_json(job_input)
    return td


def process_task(config: Config, td: TaskDefinition):
    processor = TaskProcessor(config)
    processor.prepare()
    result = processor.process_task(td)

    exchanger = Exchanger(config)
    exchanger.prepare(consumer=False, producer=True)
    exchanger.send_result(result)


def _cli():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)-15s | %(lineno)-5d | %(levelname).4s | %(message)s",
    )

    example_text = """
Example usage:
==============

BLUEPRINT_ID=1000 SETUP_ID=2000 bin/job.py
"""

    parser = argparse.ArgumentParser(
        description="Optimizer V2 Job v" + Executor.VERSION,
        epilog=example_text,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-b", "--blueprint-id", dest="blueprint_id", default=os.getenv('BLUEPRINT_ID'),
        metavar="ID", help="Blueprint ID",

    )
    parser.add_argument(
        "-s", "--setup-id", dest="setup_id", default=os.getenv('SETUP_ID'),
        metavar="ID", help="Setup ID"
    )
    parser.add_argument(
        "-p", "--params-id", dest="params_id", default=os.getenv('PARAMS_ID'),
        metavar="ID", help="Params ID"
    )
    parser.add_argument(
        "-B", "--batch-execution-id", dest="batch_execution_id",
        default=os.getenv('BATCH_EXECUTION_ID'), metavar="ID", help="BatchExecution ID"
    )
    args = parser.parse_args()

    context = {
        'blueprintId': args.blueprint_id,
        'setupId': args.setup_id,
        'paramsId': args.params_id,
        'batchExecutionId': args.batch_execution_id,
    }

    td = fetch_task_definition(context)

    config = Config()

    process_task(config, td)


_cli()
