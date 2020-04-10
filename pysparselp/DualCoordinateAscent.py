# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------
# Copyright © 2016 Martin de la Gorce <martin[dot]delagorce[hat]gmail[dot]com>

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
# -----------------------------------------------------------------------
"""LP solver using alternated  coordinate ascend on the dual."""

import copy
import time

import numpy as np

import scipy.ndimage
import scipy.sparse

from .DualGradientAscent import exact_dual_line_search
from .constraintPropagation import greedy_round


def dual_coordinate_ascent(
    x,
    LP,
    nbmaxiter=20,
    callback_func=None,
    y_eq=None,
    y_ineq=None,
    max_time=None,
    nb_iter_plot=1,
):
    """Solve LP using coordinate ascend in the dual.

    Method from 'An algorithm for large scale 0-1 integer
    programming with application to airline crew scheduling'
    we generalized it to the case where A is not 0-1 and
    the upper bounds can be greater than 1
    did not generalize and code the approximation method
    """
    np.random.seed(1)
    start = time.clock()
    # convert to slack form (augmented form)
    LP2 = copy.deepcopy(LP)
    LP = None
    # LP2.convert_to_slack_form()
    # LP2.convertTo
    LP2.convert_to_one_sided_inequality_system()

    # LP2.upperbounds=np.minimum(10,LP2.upperbounds)
    # LP2.lowerbounds=np.maximum(-10,LP2.lowerbounds)
    # y0=None
    if y_eq is None:
        y_eq = np.zeros(LP2.Aequalities.shape[0])
        # y_eq=-np.random.rand(y_eq.size)
    else:
        y_eq = y_eq.copy()
    # y_ineq=None
    if y_ineq is None:
        y_ineq = np.zeros(LP2.Ainequalities.shape[0])
        # y_ineq=np.abs(np.random.rand(y_ineq.size))
    else:
        y_ineq = y_ineq.copy()
        assert np.min(y_ineq) >= 0
    # assert (LP2.B_lower is None)

    def get_optim_x(y_eq, y_ineq, tiemethod="round"):
        c_bar = LP2.costsvector.copy()
        if LP2.Aequalities is not None:
            c_bar += y_eq * LP2.Aequalities
        if LP2.Ainequalities is not None:
            c_bar += y_ineq * LP2.Ainequalities
        x = np.zeros(LP2.costsvector.size)
        x[c_bar > 0] = LP2.lowerbounds[c_bar > 0]
        x[c_bar < 0] = LP2.upperbounds[c_bar < 0]
        #
        if tiemethod == "round":
            x[c_bar == 0] = (
                LP2.lowerbounds
                + np.random.rand(len(LP2.upperbounds))
                * (LP2.upperbounds - LP2.lowerbounds)
            )[c_bar == 0]
        elif tiemethod == "center":
            x[c_bar == 0] = 0.5 * (LP2.lowerbounds + LP2.upperbounds)[c_bar == 0]
        else:
            print("unkown tie method %s" % tiemethod)
            raise
        x[(c_bar == 0) & np.isinf(LP2.lowerbounds)] = LP2.upperbounds[
            (c_bar == 0) & np.isinf(LP2.lowerbounds)
        ]
        x[(c_bar == 0) & np.isinf(LP2.upperbounds)] = LP2.lowerbounds[
            (c_bar == 0) & np.isinf(LP2.upperbounds)
        ]
        x[
            (c_bar == 0) & np.isinf(LP2.upperbounds) & np.isinf(LP2.lowerbounds)
        ] = 0  # could take any arbitrary value
        # x[(c_bar==0) & (LP2.costsvector>0)]=LP2.lowerbounds[(c_bar==0) & (LP2.costsvector>0)]
        # x[(c_bar==0) & (LP2.costsvector<0)]=LP2.upperbounds[(c_bar==0) & (LP2.costsvector<0)]
        return c_bar, x

    def evaluate(y_eq, y_ineq):
        c_bar, x = get_optim_x(y_eq, y_ineq)
        E = -y_eq.dot(LP2.Bequalities) - y_ineq.dot(LP2.B_upper) + np.sum(x * c_bar)
        # LP2.costsvector.dot(x)+y_ineq.dot(LP2.Ainequalities*x-LP2.B_upper)
        E = (
            -y_eq.dot(LP2.Bequalities)
            - y_ineq.dot(LP2.B_upper)
            + np.sum(
                np.minimum(c_bar * LP2.upperbounds, c_bar * LP2.lowerbounds)[c_bar != 0]
            )
        )
        return E

    def exact_coordinate_line_search(Ai, bi, c_bar):
        alphas = -c_bar[Ai.indices] / Ai.data
        order = np.argsort(alphas)
        AiU = Ai.data * LP2.upperbounds[Ai.indices]
        AiL = Ai.data * LP2.lowerbounds[Ai.indices]
        tmp1 = np.minimum(AiU[order], AiL[order])
        tmp2 = np.maximum(AiU[order], AiL[order])
        tmp3 = np.cumsum(tmp2[::-1])[::-1]
        tmp4 = np.cumsum(tmp1)
        derivatives = -bi * np.ones(alphas.size + 1)
        derivatives[:-1] += tmp3
        derivatives[1:] += tmp4

        # tmp=np.abs(Ai.data[order])*(LP2.lowerbounds[Ai.indices[order]]-LP2.upperbounds[Ai.indices[order]])
        # derivatives= -LP2.Bequalities[i]-np.sum(AiL[Ai.data>0])-np.sum(AiU[Ai.data<0])\
        # +np.hstack(([0],np.cumsum(tmp)))

        k = np.searchsorted(-derivatives, 0)
        if derivatives[k] == 0 and k < len(order):
            t = np.random.rand()
            alpha_optim = (
                t * alphas[order[k]] + (1 - t) * alphas[order[k - 1]]
            )  # maybe courld draw and random valu in the interval ?
            # alpha_optim=alphas[order[k-1]]
        else:
            alpha_optim = alphas[order[k - 1]]
        return alpha_optim

    # x[c_bar==0]=0.5

    # alpha_i= vector containing the step lengths that lead to a sign change on any of the gradient component
    # when incrementing y[i]
    #
    E = evaluate(y_eq, y_ineq)

    print("iter %d energy %f" % (0, E))
    c_bar, x = get_optim_x(y_eq, y_ineq)
    direction = np.zeros(y_ineq.shape)

    timeout = False
    for niter in range(nbmaxiter):
        if timeout:
            break
        y_ineq_prev = y_ineq.copy()
        c_bar = LP2.costsvector + y_eq * LP2.Aequalities + y_ineq * LP2.Ainequalities

        grad_y_eq = LP2.Aequalities * x - LP2.Bequalities
        for i in np.nonzero(grad_y_eq)[0]:
            if i % 100 == 0:
                elapsed = time.clock() - start
                if (max_time is not None) and elapsed > max_time:
                    timeout = True
                    break

            # i=32
            # print evaluate(y)
            if False:
                import matplotlib.pyplot as plt

                y2 = y_eq.copy()
                vals = []
                alphasgrid = np.linspace(-1, 1, 1000)
                for alpha in alphasgrid:
                    y2[i] = y_eq[i] + alpha
                    vals.append(evaluate(y2, y_ineq))
                plt.plot(alphasgrid, vals, ".")
                deriv = np.diff(vals) / np.diff(alphasgrid)
                plt.plot(alphasgrid[:-1], deriv, ".")

            Ai = LP2.Aequalities[i, :]
            # c_bar=LP2.costsvector+y_eq*LP2.Aequalities+y_ineq*LP2.Ainequalities
            alpha_optim = exact_coordinate_line_search(Ai, LP2.Bequalities[i], c_bar)
            prev_y_eq = y_eq[i]
            y_eq[i] += alpha_optim
            diff_y_eq = y_eq[i] - prev_y_eq
            c_bar[Ai.indices] += diff_y_eq * Ai.data

        if timeout:
            break

        c_bar = LP2.costsvector + y_eq * LP2.Aequalities + y_ineq * LP2.Ainequalities
        nE = evaluate(y_eq, y_ineq)
        eps = 1e-10
        if nE + eps < E:
            print("not expected")

        E = nE

        c_bar, x = get_optim_x(y_eq, y_ineq)
        grad_y_ineq = LP2.Ainequalities * x - LP2.B_upper
        grad_y_ineq[y_ineq <= 0] = np.maximum(grad_y_ineq[y_ineq <= 0], 0)  #

        for i in np.nonzero(grad_y_ineq)[0]:
            if i % 100 == 0:
                elapsed = time.clock() - start
                if (max_time is not None) and elapsed > max_time:
                    timeout = True
                    break

            Ai = LP2.Ainequalities[i, :]
            if False:
                c_bar, x = get_optim_x(y_eq, y_ineq)
                grad_y_ineq = LP2.Ainequalities * x - LP2.B_upper
                grad_y_ineq[y_ineq <= 0] = np.maximum(grad_y_ineq[y_ineq <= 0], 0)  #
                alpha_optim = exact_coordinate_line_search(Ai, LP2.B_upper[i], c_bar)
                y2 = y_ineq.copy()
                vals = []
                alphasgrid = np.linspace(-4, 0, 1000)
                for alpha in alphasgrid:
                    y2[i] = y_ineq[i] + alpha
                    vals.append(evaluate(y_eq, y2))
                plt.plot(alphasgrid, vals, ".")
                deriv = np.diff(vals) / np.diff(alphasgrid)
                plt.plot(alphasgrid[:-1], deriv, ".")

            # c_bar=LP2.costsvector+y_eq*LP2.Aequalities+y_ineq*LP2.Ainequalities
            alpha_optim = exact_coordinate_line_search(Ai, LP2.B_upper[i], c_bar)

            # prev_energy=evaluate(y_eq,y_ineq)
            prev_y_ineq = y_ineq[i]
            y_ineq[i] += alpha_optim
            y_ineq[i] = max(y_ineq[i], 0)
            diff_y_ineq = y_ineq[i] - prev_y_ineq
            c_bar[Ai.indices] += diff_y_ineq * Ai.data
            # new_energy=evaluate(y_eq,y_ineq)
            # assert(new_energy>=prev_energy-1e-5)
            # assert(np.max(y_ineq)<=0)
        if timeout:
            break
        nE = evaluate(y_eq, y_ineq)
        if nE + eps < E:
            print("not expected")

        c_bar, x = get_optim_x(y_eq, y_ineq, tiemethod="center")
        x[c_bar == 0] = 0.5 * (LP2.lowerbounds + LP2.upperbounds)[
            c_bar == 0
        ] + 0.1 * np.sign(LP2.costsvector[c_bar == 0])
        if nE < E + 1e-10:
            order = np.argsort(np.abs(x - 0.5))
            fixed = c_bar != 0
            xr, valid = greedy_round(
                x, LP2, callback_func=None, maxiter=30, order=order, fixed=fixed
            )
            LP2.costsvector.dot(xr)
            x = xr

        uE = LP2.costsvector.dot(x)

        elapsed = time.clock() - start
        if (niter % nb_iter_plot) == 0:
            max_violation = max(
                np.max(LP2.Ainequalities * x - LP2.B_upper),
                np.max(np.sum(np.abs(LP2.Aequalities * x - LP2.Bequalities))),
            )
            sum_violation = np.sum(
                np.maximum(LP2.Ainequalities * x - LP2.B_upper, 0)
            ) + np.sum(np.abs(LP2.Aequalities * x - LP2.Bequalities))
            print(
                "iter %d time %3.1f dual energy %f, primal %f max violation %f sum_violation %f"
                % (niter, elapsed, nE, uE, max_violation, sum_violation)
            )
            if max_violation == 0:

                print("found feasible primal solution with energy %f" % uE)
                if uE == nE:
                    print("found optimal solution , stop")
                    break
                if uE < nE:
                    print("not expected")
                if nE < E + 1e-10:
                    print("will not find better solution , stop")
                    break

        E = nE
        if callback_func is not None:
            callback_func(niter, x, 0, 0, elapsed, 0, 0)
        if False:
            diff = y_ineq - y_ineq_prev
            direction = scipy.sparse.csr.csr_matrix(direction * 0.9 + 0.1 * diff)
            coef_length = exact_dual_line_search(
                direction,
                LP2.Ainequalities,
                LP2.B_upper,
                c_bar,
                LP2.upperbounds,
                LP2.lowerbounds,
            )
            y_ineq = np.array(y_ineq + coef_length * direction).flatten()
            y_ineq = np.maximum(y_ineq, 0)
            # y_ineq=y_ineq+*0.1
            # y_ineq=np.maximum(y_ineq, 0)
            print("iter %d energy %f" % (niter, evaluate(y_eq, y_ineq)))

        if (max_time is not None) and elapsed > max_time:
            timeout = True
            break
    max_violation = max(
        np.max(LP2.Ainequalities * x - LP2.B_upper),
        np.max(np.sum(np.abs(LP2.Aequalities * x - LP2.Bequalities))),
    )
    sum_violation = np.sum(np.maximum(LP2.Ainequalities * x - LP2.B_upper, 0)) + np.sum(
        np.abs(LP2.Aequalities * x - LP2.Bequalities)
    )
    print(
        "iter %d time %3.1f dual energy %f, primal %f max violation %f sum_violation %f"
        % (niter, elapsed, nE, uE, max_violation, sum_violation)
    )
    return x, y_eq, y_ineq
