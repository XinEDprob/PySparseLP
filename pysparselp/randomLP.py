"""Module to generate random LP problems."""

import copy

import matplotlib.pyplot as plt

import numpy as np

import scipy.sparse

from . import SparseLP, solving_methods


def rand_sparse(shape, sparsity):
    if isinstance(shape, tuple) or isinstance(shape, list):
        return (
            np.round(np.random.randn(*shape) * 100)
            * (np.random.rand(*shape) < sparsity)
            / 100
        )
    else:
        return (
            np.round(np.random.randn(shape) * 100)
            * (np.random.rand(shape) < sparsity)
            / 100
        )


def generate_random_lp(nbvar, n_eq, n_ineq, sparsity):

    # maybe could have a look at https://www.jstor.org/stable/3689906?seq=1#page_scan_tab_contents
    # https://deepblue.lib.umich.edu/bitstream/handle/2027.42/3549/bam8969.0001.001.pdf
    feasibleX = rand_sparse(nbvar, sparsity=1)

    if n_ineq > 0:
        while True:  # make sure the mattrix is not empy=ty
            A_ineq = scipy.sparse.csr_matrix(rand_sparse((n_ineq, nbvar), sparsity))
            keep = (
                (A_ineq != 0).dot(np.ones(nbvar))
            ) >= 2  # keep only rows with at least two non zeros values
            if np.sum(keep) >= 1:
                break
        bmin = A_ineq.dot(feasibleX)
        b_upper = (
            np.ceil((bmin + abs(rand_sparse(n_ineq, sparsity))) * 1000) / 1000
        )  # make v feasible
        b_lower = None  # bmin-abs(rand_sparse(n_ineq,sparsity))
        A_ineq = A_ineq[keep, :]
        b_upper = b_upper[keep]

    costs = rand_sparse(nbvar, sparsity=1)

    t = rand_sparse(nbvar, sparsity=1)
    lowerbounds = feasibleX + np.minimum(0, t)
    upperbounds = feasibleX + np.maximum(0, t)

    LP = SparseLP()
    LP.add_variables_array(
        nbvar, lowerbounds=lowerbounds, upperbounds=upperbounds, costs=costs
    )
    if n_eq > 0:
        Aeq = scipy.sparse.csr_matrix(rand_sparse((n_eq, nbvar), sparsity))
        Beq = Aeq.dot(feasibleX)
        keep = (
            (Aeq != 0).dot(np.ones(nbvar))
        ) >= 2  # keep only rows with at least two non zeros values
        Aeq = Aeq[keep, :]
        Beq = Beq[keep]
        if Aeq.indices.size > 0:
            LP.add_equality_constraints_sparse(Aeq, Beq)
    if n_ineq > 0 and A_ineq.indices.size > 0:
        LP.add_constraints_sparse(A_ineq, b_lower, b_upper)

    assert LP.check_solution(feasibleX)
    return LP, feasibleX


if __name__ == "__main__":
    plt.ion()

    LP, v = generate_random_lp(nbvar=30, n_eq=1, n_ineq=30, sparsity=0.2)
    LP2 = copy.deepcopy(LP)
    LP2.convert_to_one_sided_inequality_system()
    scipySol, elapsed = LP2.solve(
        method="ScipyLinProg", force_integer=False, getTiming=True, nb_iter=100000
    )
    costScipy = scipySol.dot(LP2.costsvector.T)
    maxv = LP2.max_constraint_violation(scipySol)
    if maxv > 1e-8:
        print("not expected")
        raise

    groundTruth = scipySol
    solving_methods2 = list(set(solving_methods) - set(["dual_gradient_ascent"]))

    f, axarr = plt.subplots(3, sharex=True)
    axarr[0].set_title("mean absolute distance to solution")
    axarr[1].set_title("maximum constraint violation")
    axarr[2].set_title("difference with optimum value")
    max_time = 2
    for method in solving_methods2:
        sol1, elapsed = LP2.solve(
            method=method, max_time=max_time, groundTruth=groundTruth
        )
        axarr[0].semilogy(
            LP2.opttime_curve,
            np.maximum(LP2.distanceToGroundTruth, 1e-18),
            label=method,
        )
        axarr[1].semilogy(
            LP2.opttime_curve, np.maximum(LP2.max_violated_constraint, 1e-18)
        )
        axarr[2].semilogy(
            LP2.opttime_curve, np.maximum(LP2.pobj_curve - costScipy, 1e-18)
        )
        axarr[0].legend()
        plt.show()
    print("done")
