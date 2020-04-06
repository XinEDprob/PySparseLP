from pysparselp.examples.example1 import run
import json
import numpy as np
import numpy.testing
import os

__folder__ = os.path.dirname(__file__)


def trim_length(a, b):
    min_len = min(len(a), len(b))
    return a[:min_len], b[:min_len]


def test_example1(update_results=True):

    distanceToGroundTruthCurves = run(display=False)

    curves_json_file = os.path.join(__folder__, 'example1_curves.json')
    if update_results:
        with open(curves_json_file, 'w') as f:
            json.dump(distanceToGroundTruthCurves, f)

    with open(curves_json_file, 'r') as f:
        distanceToGroundTruthCurves_expected = json.load(f)

    for k, v1 in distanceToGroundTruthCurves.items():
        v2 = distanceToGroundTruthCurves_expected[k]
        tv1, tv2 = trim_length(v1, v2)
        max_diff = np.max(np.abs(np.array(tv1) - np.array(tv2)))
        print(f'max diff {k} = {max_diff}')
        numpy.testing.assert_almost_equal(*trim_length(v1, v2))


if __name__ == "__main__":
    test_example1()