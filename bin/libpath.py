import os
import sys

# There has to be a better way to do this.
sys.path.append(
    os.path.realpath(
        os.path.join(
            os.path.dirname(
                os.path.realpath(__file__)
            ),
            os.pardir
        )
    )
)